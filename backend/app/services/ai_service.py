"""AI service: campaign analysis and community intelligence.

Two guarantees this module provides:

1. **The model never defines the structure.** Every LLM response is parsed and
   validated against a Pydantic schema. Invalid output is retried once, then
   replaced by a deterministic heuristic and stored as DEGRADED — the record is
   never corrupted by whatever the model felt like emitting.
2. **AI is decision support.** Nothing here approves a campaign. The disclaimer
   travels with every result.

Provider selection is environment-driven (`AI_PROVIDER=mock|gemma|nvidia`), so the demo
runs with no credentials and production swaps in a real endpoint without touching
callers.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import AnalysisStatus, AnalysisType, EventType
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.community import AIAnalysis, AICommunityInsight
from app.services import audit_service, document_service

logger = get_logger(__name__)

AI_DISCLAIMER = (
    "AI analysis is provided as decision support and is not a guarantee of "
    "campaign success or legitimacy."
)

_PROMPT_DIRS = [
    Path(__file__).resolve().parents[3] / "ai" / "prompts",  # repo root /ai/prompts
    Path(__file__).resolve().parents[2] / "ai" / "prompts",  # backend-local copy
    Path("/app/ai/prompts"),  # container mount
]


# --------------------------------------------------------------------------
# Validated model output
# --------------------------------------------------------------------------
def _clamp_score(value: Any) -> int:
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return 50


class CampaignAnalysisResult(BaseModel):
    feasibility_score: int = 50
    problem_clarity_score: int = 50
    impact_score: int = 50
    risk_score: int = 50
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    questions_for_creator: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)

    @field_validator(
        "feasibility_score", "problem_clarity_score", "impact_score", "risk_score", mode="before"
    )
    @classmethod
    def _scores(cls, value):
        return _clamp_score(value)

    @field_validator(
        "strengths", "concerns", "recommendations", "questions_for_creator",
        "missing_information", mode="before",
    )
    @classmethod
    def _lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item)[:200] for item in list(value)[:6] if str(item).strip()]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, value):
        return str(value or "")[:1200]

    @property
    def risk_level(self) -> str:
        if self.risk_score >= 70:
            return "High"
        return "Medium" if self.risk_score >= 40 else "Low"


class CommunityInsightResult(BaseModel):
    community_summary: str = ""
    positive_themes: list[str] = Field(default_factory=list)
    top_concerns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    questions_from_community: list[str] = Field(default_factory=list)
    risk_change: str = ""

    @field_validator(
        "positive_themes", "top_concerns", "recommendations", "questions_from_community",
        mode="before",
    )
    @classmethod
    def _lists(cls, value):
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        return [str(item)[:200] for item in list(value)[:6] if str(item).strip()]

    @field_validator("community_summary", "risk_change", mode="before")
    @classmethod
    def _text(cls, value):
        return str(value or "")[:1500]


# --------------------------------------------------------------------------
# Prompt loading
# --------------------------------------------------------------------------
@lru_cache(maxsize=8)
def load_prompt(name: str) -> tuple[str, str]:
    """Return (system, user_template) from ai/prompts/<name>.md."""
    for directory in _PROMPT_DIRS:
        path = directory / f"{name}.md"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            system = _section(text, "SYSTEM")
            user = _section(text, "USER")
            if system and user:
                return system, user
    logger.warning("prompt_file_missing", prompt=name)
    return _FALLBACK_PROMPTS[name]


def _section(text: str, heading: str) -> str:
    match = re.search(rf"^##\s+{heading}\s*$(.*?)(?=^##\s+|\Z)", text, re.M | re.S)
    return match.group(1).strip() if match else ""


_FALLBACK_PROMPTS: dict[str, tuple[str, str]] = {
    "campaign_analysis": (
        "You are a crowdfunding campaign analyst. Reply with one JSON object only, "
        "matching keys: feasibility_score, problem_clarity_score, impact_score, "
        "risk_score (0-100), summary, strengths, concerns, recommendations, "
        "questions_for_creator, missing_information.",
        "Analyse this campaign.\nTitle: {title}\nCategory: {category}\n"
        "Target: INR {target_amount}\nProblem: {problem_statement}\n"
        "Solution: {proposed_solution}\nDescription: {description}\n"
        "Attached documents (creator claims, not verified records):\n"
        "{supporting_documents}",
    ),
    "sentiment": (
        "You are a sentiment classifier for crowdfunding feedback. Reply with one "
        "JSON object only: {\"results\": [{\"index\": 0, \"label\": "
        "\"POSITIVE|NEUTRAL|NEGATIVE\", \"score\": 0.9}]}. Exactly one entry per "
        "input index.",
        "Classify each comment.\n\n{comments}",
    ),
    "community_insights": (
        "You are a community analyst. Reply with one JSON object only, matching keys: "
        "community_summary, positive_themes, top_concerns, recommendations, "
        "questions_from_community, risk_change.",
        "Campaign: {title}\nFeedback: {feedback_count}\n"
        "Positive {positive_percentage}% / Neutral {neutral_percentage}% / "
        "Negative {negative_percentage}%\nAspects: {aspect_distribution}\n"
        "Comments:\n{sample_comments}",
    ),
}


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
class CampaignAnalysisProvider(ABC):
    name: str = "abstract"
    model: str = "abstract"

    @abstractmethod
    def analyze_campaign(self, payload: dict[str, Any]) -> CampaignAnalysisResult: ...

    @abstractmethod
    def summarize_community(self, payload: dict[str, Any]) -> CommunityInsightResult: ...


class OpenAICompatibleProvider(CampaignAnalysisProvider):
    """One chat client for every OpenAI-compatible endpoint we support.

    Ollama, vLLM, a hosted gateway and NVIDIA NIM all speak the same
    `/chat/completions` dialect, so the differences that actually matter —
    endpoint, key, model, whether JSON mode is honoured — are constructor
    arguments rather than separate implementations.
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        json_mode: str = "auto",
        max_tokens: int | None = None,
        temperature: float | None = None,
    ):
        self.name = name
        self.model = model
        self._base_url = (base_url or "").rstrip("/")
        self._timeout = timeout
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._json_mode = json_mode
        self._headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def _body(self, system: str, user: str, json_mode: bool) -> dict[str, Any]:
        """Minimal by default: model and messages only.

        Every extra field is one more thing a given model in a large catalogue
        can reject or mishandle — reasoning models in particular spend their
        budget thinking, so a `max_tokens` meant for a plain model truncates them
        before they emit anything. Extras are sent only when explicitly asked for.
        """
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if self._temperature is not None:
            body["temperature"] = self._temperature
        if self._max_tokens:
            body["max_tokens"] = self._max_tokens
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        return body

    def _chat(self, system: str, user: str, json_mode: bool) -> str:
        response = httpx.post(
            f"{self._base_url}/chat/completions",
            headers=self._headers,
            json=self._body(system, user, json_mode),
            timeout=self._timeout,
        )
        if response.status_code == 404:
            raise RuntimeError(
                f"Model {self.model!r} is not available on this account at "
                f"{self._base_url}. List what your key can reach with "
                f"GET {self._base_url}/models, then set the matching env model."
            )
        response.raise_for_status()
        data = response.json()
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected chat response shape: {str(data)[:300]}") from exc
        content = message.get("content") or ""
        if not content.strip():
            # Reasoning models put their scratchpad in reasoning_content and can
            # leave content empty when they run out of budget mid-thought.
            finish = (data.get("choices") or [{}])[0].get("finish_reason")
            raise RuntimeError(f"Model returned empty content (finish_reason={finish!r}).")
        return content

    def _attempts(self) -> list[bool]:
        """Whether to send response_format on each successive attempt.

        `auto` asks plainly first — the prompt already demands JSON and
        extract_json recovers it from prose — and only escalates to JSON mode if
        that came back unparseable. That order keeps the request minimal for the
        models that need it minimal, without giving up the strictness for models
        that honour it.
        """
        if self._json_mode == "on":
            return [True, True]
        if self._json_mode == "off":
            return [False, False]
        return [False, True]

    def _call_json(self, prompt_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        system, template = load_prompt(prompt_name)
        user = template.format_map(_SafeDict(payload))
        return self.call_json(system, user, label=prompt_name)

    def call_json(self, system: str, user: str, *, label: str = "adhoc") -> dict[str, Any]:
        """Public entry point for callers that build their own messages.

        Sentiment classification uses this so it inherits the retry, the JSON
        recovery and the 404 diagnosis rather than reimplementing an HTTP client.
        """
        last_error: Exception | None = None
        for attempt, json_mode in enumerate(self._attempts(), start=1):
            try:
                return extract_json(self._chat(system, user, json_mode))
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_call_failed",
                    provider=self.name,
                    model=self.model,
                    prompt=label,
                    attempt=attempt,
                    json_mode=json_mode,
                    error=str(exc)[:300],
                )
        raise RuntimeError(f"{self.name} call failed after retry: {last_error}")

    def analyze_campaign(self, payload: dict[str, Any]) -> CampaignAnalysisResult:
        return CampaignAnalysisResult.model_validate(
            self._call_json("campaign_analysis", payload)
        )

    def summarize_community(self, payload: dict[str, Any]) -> CommunityInsightResult:
        return CommunityInsightResult.model_validate(
            self._call_json("community_insights", payload)
        )


class GemmaProvider(OpenAICompatibleProvider):
    """Gemma over any OpenAI-compatible endpoint (Ollama, vLLM, hosted gateway).

    Endpoint, key and model all come from env, so switching from a local Gemma to
    a hosted one is configuration, not code.
    """

    def __init__(self):
        super().__init__(
            name="gemma",
            base_url=settings.gemma_base_url,
            api_key=settings.gemma_api_key,
            model=settings.gemma_model,
            timeout=settings.gemma_timeout_seconds,
        )


class NvidiaProvider(OpenAICompatibleProvider):
    """NVIDIA NIM — the hosted build.nvidia.com gateway or a self-hosted NIM.

    Both expose an OpenAI-compatible API, so the only thing that changes between
    them is `NVIDIA_BASE_URL`. The model catalogue is wide and JSON-mode support
    varies across it, hence the auto-downgrade in the base class.
    """

    def __init__(self):
        if not settings.nvidia_api_key and "api.nvidia.com" in settings.nvidia_base_url:
            # Self-hosted NIM needs no key; the hosted gateway always does.
            raise RuntimeError(
                "NVIDIA_API_KEY is not set. Create a key at build.nvidia.com and set "
                "NVIDIA_API_KEY, or point NVIDIA_BASE_URL at a self-hosted NIM."
            )
        super().__init__(
            name="nvidia",
            base_url=settings.nvidia_base_url,
            api_key=settings.nvidia_api_key,
            model=settings.nvidia_model,
            timeout=settings.nvidia_timeout_seconds,
            json_mode=settings.nvidia_json_mode,
            max_tokens=settings.nvidia_max_tokens,
            temperature=settings.nvidia_temperature,
        )


class MockAnalysisProvider(CampaignAnalysisProvider):
    """Deterministic heuristic analyst used when no LLM is configured.

    This is not a canned response: it reads the actual proposal and scores it on
    observable properties (specificity, presence of quantities and timelines,
    budget-to-ambition ratio, section depth). Two different campaigns get two
    genuinely different analyses, which is what makes the offline demo honest.
    """

    name = "mock"
    model = "crowdwise-heuristic-v1"

    _PLAN_MARKERS = (
        "phase", "milestone", "timeline", "month", "week", "pilot", "deploy",
        "manufactur", "partner", "distribut", "roadmap", "prototype",
    )
    _TEAM_MARKERS = ("team", "founder", "engineer", "experience", "worked", "led", "ngo")
    _IMPACT_MARKERS = (
        "communit", "village", "household", "student", "farmer", "families",
        "people", "women", "school", "rural", "access",
    )
    _SCALE_MARKERS = ("scale", "expand", "replicat", "district", "state", "nationwide")

    def analyze_campaign(self, payload: dict[str, Any]) -> CampaignAnalysisResult:
        problem = str(payload.get("problem_statement") or "")
        solution = str(payload.get("proposed_solution") or "")
        description = str(payload.get("description") or "")
        impact = str(payload.get("expected_impact") or "")
        blob = " ".join([problem, solution, description, impact]).lower()

        try:
            target = float(str(payload.get("target_amount") or 0))
        except ValueError:
            target = 0.0
        days = int(payload.get("days_remaining") or 30)

        has_numbers = len(re.findall(r"\d", blob))
        plan_hits = sum(1 for m in self._PLAN_MARKERS if m in blob)
        team_hits = sum(1 for m in self._TEAM_MARKERS if m in blob)
        impact_hits = sum(1 for m in self._IMPACT_MARKERS if m in blob)
        scale_hits = sum(1 for m in self._SCALE_MARKERS if m in blob)

        problem_clarity = _bounded(
            45 + min(len(problem) // 18, 30) + min(has_numbers * 2, 16), 20, 96
        )
        feasibility = _bounded(
            40 + plan_hits * 6 + min(len(solution) // 25, 20) + (6 if team_hits else 0), 15, 94
        )
        impact_score = _bounded(
            42 + impact_hits * 6 + scale_hits * 4 + min(len(impact) // 20, 14), 20, 95
        )

        risk = 46
        risk -= plan_hits * 4
        risk -= 6 if team_hits >= 2 else 0
        risk += 12 if target >= 1_000_000 else 0
        risk += 8 if target >= 5_000_000 else 0
        risk += 10 if days <= 21 else 0
        risk += 12 if len(description) < 400 else 0
        risk -= 5 if has_numbers > 12 else 0
        risk_score = _bounded(risk, 12, 92)

        strengths: list[str] = []
        if problem_clarity >= 70:
            strengths.append("Problem is described concretely with supporting detail.")
        if impact_hits >= 3:
            strengths.append("Clear community benefit with an identified beneficiary group.")
        if plan_hits >= 3:
            strengths.append("Execution path includes phases, partners or milestones.")
        if team_hits >= 2:
            strengths.append("Proposal references relevant team background.")
        if has_numbers > 10:
            strengths.append("Quantified claims make the proposal verifiable.")

        concerns: list[str] = []
        if target >= 1_000_000 and plan_hits < 4:
            concerns.append("Funding target is large relative to the detail of the delivery plan.")
        if team_hits < 2:
            concerns.append("Team experience and delivery capability are not evidenced.")
        if len(description) < 400:
            concerns.append("Proposal is brief; several execution details are unstated.")
        if days <= 21:
            concerns.append("Short funding window leaves little room to build momentum.")
        if "budget" not in blob and "cost" not in blob:
            concerns.append("No budget breakdown for how the funds will be spent.")
        if scale_hits == 0:
            concerns.append("Path beyond the initial deployment is not described.")

        recommendations = [
            "Publish a line-item budget showing how the target amount is allocated.",
            "Add a milestone timeline with dates the community can hold you to.",
        ]
        if team_hits < 2:
            recommendations.append("Introduce the team and their relevant delivery experience.")
        if scale_hits == 0:
            recommendations.append("Describe what happens after the first deployment.")

        questions = [
            "How was the funding target calculated?",
            "Who manufactures, builds or delivers the solution, and are they committed?",
            "What is the plan if only part of the target is raised?",
        ]
        missing = []
        if "budget" not in blob and "cost" not in blob:
            missing.append("Budget breakdown")
        if team_hits < 2:
            missing.append("Team credentials")
        if plan_hits < 3:
            missing.append("Delivery timeline")
        if "maintain" not in blob and "support" not in blob:
            missing.append("Post-deployment maintenance plan")

        summary = (
            f"The proposal presents {'a clearly defined' if problem_clarity >= 70 else 'a partially defined'} "
            f"problem with {'a detailed' if plan_hits >= 3 else 'a high-level'} solution. "
            f"Feasibility scores {feasibility} and estimated execution risk is "
            f"{'high' if risk_score >= 70 else 'medium' if risk_score >= 40 else 'low'} "
            f"given the INR {target:,.0f} target."
        )

        return CampaignAnalysisResult(
            feasibility_score=feasibility,
            problem_clarity_score=problem_clarity,
            impact_score=impact_score,
            risk_score=risk_score,
            summary=summary,
            strengths=strengths[:5] or ["Proposal is submitted with the required sections."],
            concerns=concerns[:5] or ["No material concerns detected in the written proposal."],
            recommendations=recommendations[:5],
            questions_for_creator=questions[:5],
            missing_information=missing[:5],
        )

    def summarize_community(self, payload: dict[str, Any]) -> CommunityInsightResult:
        positive = float(payload.get("positive_percentage") or 0)
        negative = float(payload.get("negative_percentage") or 0)
        count = int(payload.get("feedback_count") or 0)
        aspects = payload.get("aspect_ranking") or []
        top_aspect = aspects[0][0] if aspects else "the campaign overall"
        rating = payload.get("average_rating") or 0

        if positive >= 60:
            mood = "predominantly positive"
        elif positive >= 40:
            mood = "mixed but leaning positive"
        elif negative >= 40:
            mood = "predominantly critical"
        else:
            mood = "mixed"

        summary = (
            f"Community sentiment is {mood} across {count} feedback items, averaging "
            f"{rating}/5. The most discussed theme is {top_aspect}. "
            f"{'Support centres on the social impact of the project.' if positive >= 50 else 'Contributors want more detail before committing further.'}"
        )
        concerns = [f"{name} is the most frequently raised theme." for name, _ in aspects[:3]]
        if negative >= 20:
            concerns.append("A meaningful minority express doubts about delivery.")
        return CommunityInsightResult(
            community_summary=summary,
            positive_themes=(
                ["Social impact is widely appreciated.", "Contributors find the idea worthwhile."]
                if positive >= 40
                else ["Some contributors see potential in the idea."]
            ),
            top_concerns=concerns[:4] or ["No dominant concern has emerged yet."],
            recommendations=[
                f"Respond publicly to questions about {top_aspect.lower()}.",
                "Post a progress update so contributors can see momentum.",
            ],
            questions_from_community=[
                "How was the funding target arrived at?",
                "What happens if the target is not met?",
            ],
            risk_change=(
                "Community feedback modestly increases perceived risk."
                if negative >= 25
                else "Community feedback does not materially change perceived risk."
            ),
        )


class _SafeDict(dict):
    """format_map that leaves unknown placeholders visible instead of raising."""

    def __missing__(self, key):
        return ""


def _bounded(value: float, low: int, high: int) -> int:
    return int(max(low, min(high, round(value))))


def extract_json(raw: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Small models still wrap JSON in prose or code fences even when asked not to;
    recovering here is cheaper than a retry.
    """
    text = (raw or "").strip()
    # Reasoning models (several NIM ones) prepend a <think> block whose braces
    # would otherwise be mistaken for the start of the payload.
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S | re.I).strip()
    text = re.sub(r"^<think>.*", "", text, flags=re.S | re.I).strip() or text
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, depth = text.find("{"), 0
    if start == -1:
        raise ValueError("No JSON object found in model response.")
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise ValueError("Unterminated JSON object in model response.")


_PROVIDERS: dict[str, type[CampaignAnalysisProvider]] = {
    "gemma": GemmaProvider,
    "nvidia": NvidiaProvider,
    "mock": MockAnalysisProvider,
}

_provider: CampaignAnalysisProvider | None = None


def _build_provider(name: str) -> CampaignAnalysisProvider:
    """Never let a misconfigured provider take the app down at import time."""
    factory = _PROVIDERS.get(name, MockAnalysisProvider)
    try:
        return factory()
    except Exception as exc:
        logger.error("ai_provider_init_failed", provider=name, error=str(exc))
        return MockAnalysisProvider()


def get_provider() -> CampaignAnalysisProvider:
    global _provider
    if _provider is None:
        _provider = _build_provider(settings.ai_provider)
        logger.info("ai_provider_selected", provider=_provider.name, model=_provider.model)
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None


_FALLBACK = MockAnalysisProvider()


# --------------------------------------------------------------------------
# Service operations
# --------------------------------------------------------------------------
def _campaign_payload(campaign: Campaign) -> dict[str, Any]:
    """Only creator-authored proposal fields and their attachments.

    No personal data leaves the DB. Documents are creator-authored evidence, and
    what reaches the model is the extracted text, never the file itself.
    """
    days_remaining = max((campaign.deadline - utcnow()).days, 0) if campaign.deadline else 0
    return {
        "title": campaign.title,
        "category": campaign.category,
        "target_amount": f"{Decimal(campaign.target_amount):,.0f}",
        "minimum_contribution": str(campaign.minimum_contribution),
        "days_remaining": days_remaining,
        "short_description": campaign.short_description,
        "problem_statement": campaign.problem_statement,
        "proposed_solution": campaign.proposed_solution,
        "expected_impact": campaign.expected_impact or "Not specified.",
        "description": campaign.description,
        # Both visibility tiers reach the model. The tier governs who *else* may
        # read a file, not whether the analyst may — a creator who attaches a
        # quote to back a number wants the number judged against it.
        "supporting_documents": document_service.prompt_section(campaign),
    }


def analyze_campaign(db: Session, campaign: Campaign, actor_id: int | None = None) -> AIAnalysis:
    """Run campaign analysis and persist it. Never raises on model failure."""
    provider = get_provider()
    payload = _campaign_payload(campaign)
    status = AnalysisStatus.COMPLETED
    error: str | None = None

    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.AI_ANALYSIS_STARTED,
        actor_id=actor_id,
        metadata={"provider": provider.name, "model": provider.model},
    )

    try:
        result = provider.analyze_campaign(payload)
        model_name, provider_name = provider.model, provider.name
    except Exception as exc:
        # The proposal is not held hostage by an unavailable model: fall back to
        # the heuristic analyst and mark the record DEGRADED so the admin knows.
        logger.error("ai_analysis_failed", campaign_id=campaign.id, error=str(exc))
        result = _FALLBACK.analyze_campaign(payload)
        model_name, provider_name = _FALLBACK.model, _FALLBACK.name
        status, error = AnalysisStatus.DEGRADED, str(exc)[:500]

    analysis = AIAnalysis(
        campaign_id=campaign.id,
        type=AnalysisType.CAMPAIGN,
        model=model_name,
        provider=provider_name,
        status=status,
        feasibility_score=result.feasibility_score,
        problem_clarity_score=result.problem_clarity_score,
        impact_score=result.impact_score,
        risk_score=result.risk_score,
        strengths=result.strengths,
        concerns=result.concerns,
        recommendations=result.recommendations,
        questions_for_creator=result.questions_for_creator,
        missing_information=result.missing_information,
        summary=result.summary,
        raw_result=result.model_dump(),
        error=error,
    )
    db.add(analysis)
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=(
            EventType.AI_ANALYSIS_COMPLETED
            if status == AnalysisStatus.COMPLETED
            else EventType.AI_ANALYSIS_FAILED
        ),
        actor_id=actor_id,
        metadata={
            "status": str(status),
            "risk_score": result.risk_score,
            "feasibility_score": result.feasibility_score,
            "model": model_name,
        },
    )
    return analysis


def latest_analysis(db: Session, campaign_id: int) -> AIAnalysis | None:
    stmt = (
        select(AIAnalysis)
        .where(AIAnalysis.campaign_id == campaign_id, AIAnalysis.type == AnalysisType.CAMPAIGN)
        .order_by(AIAnalysis.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def latest_insight(db: Session, campaign_id: int) -> AICommunityInsight | None:
    stmt = (
        select(AICommunityInsight)
        .where(AICommunityInsight.campaign_id == campaign_id)
        .order_by(AICommunityInsight.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def generate_community_insights(
    db: Session, campaign: Campaign, actor_id: int | None = None
) -> AICommunityInsight | None:
    """Aggregate sentiment, then make exactly one LLM call for the whole community."""
    from app.services import sentiment_service  # local import avoids a cycle

    stats = sentiment_service.aggregate_campaign_sentiment(db, campaign.id)
    if stats.feedback_count == 0:
        return None

    payload = {
        "title": campaign.title,
        "target_amount": f"{Decimal(campaign.target_amount):,.0f}",
        "raised_amount": f"{Decimal(campaign.raised_amount):,.0f}",
        "funding_percentage": campaign.funding_percentage,
        "feedback_count": stats.feedback_count,
        "average_rating": stats.average_rating,
        "positive_percentage": stats.positive_percentage,
        "neutral_percentage": stats.neutral_percentage,
        "negative_percentage": stats.negative_percentage,
        "aspect_distribution": "\n".join(
            f"- {name}: {pct}%" for name, pct in stats.aspect_ranking
        ),
        "aspect_ranking": stats.aspect_ranking,
        # Anonymised sample only — never the author, never the whole corpus.
        "sample_comments": "\n".join(f"- {text}" for text in stats.sample_comments),
    }

    provider = get_provider()
    status, error = AnalysisStatus.COMPLETED, None
    try:
        result = provider.summarize_community(payload)
        model_name, provider_name = provider.model, provider.name
    except Exception as exc:
        logger.error("community_insight_failed", campaign_id=campaign.id, error=str(exc))
        result = _FALLBACK.summarize_community(payload)
        model_name, provider_name = _FALLBACK.model, _FALLBACK.name
        status, error = AnalysisStatus.DEGRADED, str(exc)[:500]

    insight = AICommunityInsight(
        campaign_id=campaign.id,
        positive_percentage=stats.positive_percentage,
        neutral_percentage=stats.neutral_percentage,
        negative_percentage=stats.negative_percentage,
        average_rating=stats.average_rating,
        feedback_count=stats.feedback_count,
        top_concerns=result.top_concerns,
        positive_themes=result.positive_themes,
        aspect_distribution=dict(stats.aspect_ranking),
        community_summary=result.community_summary,
        recommendations=result.recommendations,
        questions_from_community=result.questions_from_community,
        risk_change=result.risk_change,
        model=model_name,
        provider=provider_name,
        status=status,
    )
    if error:
        insight.risk_change = insight.risk_change or ""
    db.add(insight)
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.COMMUNITY_INSIGHTS_GENERATED,
        actor_id=actor_id,
        metadata={"feedback_count": stats.feedback_count, "status": str(status)},
    )
    return insight


def should_refresh_insights(db: Session, campaign: Campaign) -> bool:
    """Cache until enough new feedback has arrived to change the picture."""
    from app.services import sentiment_service

    existing = latest_insight(db, campaign.id)
    if existing is None:
        return True
    current_count = sentiment_service.feedback_count(db, campaign.id)
    return (current_count - existing.feedback_count) >= settings.community_insight_refresh_threshold
