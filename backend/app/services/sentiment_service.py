"""Sentiment and aspect analysis.

Feedback is classified once, when it is created (via a background task) — never
on dashboard render. The classifier is cheap and per-item; the LLM only ever sees
the aggregate produced here.

`XLMRobertaProvider` is the real multilingual model (lazy-imported so the demo
machine needs no ML wheels). `MockSentimentProvider` is a lexicon classifier that
genuinely reads the text, so the offline demo produces real, differentiated
sentiment rather than canned percentages.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import ASPECT_LABELS, EventType, FeedbackAspect, Sentiment
from app.core.logging import get_logger
from app.models.community import Feedback
from app.services import audit_service

logger = get_logger(__name__)


@dataclass(slots=True)
class SentimentResult:
    label: str
    score: float
    model: str


@dataclass(slots=True)
class CampaignSentimentStats:
    feedback_count: int = 0
    analyzed_count: int = 0
    positive_percentage: float = 0.0
    neutral_percentage: float = 0.0
    negative_percentage: float = 0.0
    average_rating: float = 0.0
    aspect_ranking: list[tuple[str, float]] = field(default_factory=list)
    sample_comments: list[str] = field(default_factory=list)
    rating_distribution: dict[int, int] = field(default_factory=dict)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
class SentimentProvider(ABC):
    name: str = "abstract"
    model: str = "abstract"

    @abstractmethod
    def classify(self, text: str) -> SentimentResult: ...

    def classify_batch(self, texts: list[str]) -> list[SentimentResult]:
        return [self.classify(text) for text in texts]


class XLMRobertaProvider(SentimentProvider):
    """Multilingual sentiment via XLM-RoBERTa.

    Loaded lazily and once: the pipeline is expensive to construct and must never
    be built inside a request handler.
    """

    name = "xlm-roberta"

    _LABEL_MAP = {
        "positive": Sentiment.POSITIVE,
        "neutral": Sentiment.NEUTRAL,
        "negative": Sentiment.NEGATIVE,
        "label_0": Sentiment.NEGATIVE,
        "label_1": Sentiment.NEUTRAL,
        "label_2": Sentiment.POSITIVE,
    }

    def __init__(self):
        self.model = settings.sentiment_model
        self._pipeline = None

    def _ensure_pipeline(self):
        if self._pipeline is None:
            from transformers import pipeline  # noqa: PLC0415

            logger.info("loading_sentiment_model", model=self.model)
            self._pipeline = pipeline(
                "sentiment-analysis",
                model=self.model,
                tokenizer=self.model,
                device=-1 if settings.sentiment_device == "cpu" else 0,
                truncation=True,
                max_length=512,
            )
        return self._pipeline

    def classify(self, text: str) -> SentimentResult:
        prediction = self._ensure_pipeline()(preprocess(text))[0]
        label = self._LABEL_MAP.get(str(prediction["label"]).lower(), Sentiment.NEUTRAL)
        return SentimentResult(
            label=str(label), score=round(float(prediction["score"]), 4), model=self.model
        )

    def classify_batch(self, texts: list[str]) -> list[SentimentResult]:
        predictions = self._ensure_pipeline()([preprocess(t) for t in texts])
        return [
            SentimentResult(
                label=str(self._LABEL_MAP.get(str(p["label"]).lower(), Sentiment.NEUTRAL)),
                score=round(float(p["score"]), 4),
                model=self.model,
            )
            for p in predictions
        ]


class MockSentimentProvider(SentimentProvider):
    """Lexicon-and-negation classifier used when the ML wheels are absent.

    It handles negation ("not great"), intensifiers, and a small Hindi/Hinglish
    vocabulary, which is enough for the multilingual story to be real in a demo
    rather than decorative.
    """

    name = "mock"
    model = "crowdwise-lexicon-v1"

    _POSITIVE = {
        "good", "great", "excellent", "amazing", "love", "loved", "wonderful", "brilliant",
        "impressive", "useful", "helpful", "strong", "solid", "promising", "innovative",
        "needed", "important", "support", "supporting", "happy", "best", "fantastic",
        "clear", "transparent", "genuine", "trustworthy", "affordable", "sustainable",
        "accha", "badhiya", "shandaar", "zabardast", "sahi", "behtareen",
    }
    _NEGATIVE = {
        "bad", "poor", "terrible", "awful", "worst", "waste", "scam", "fraud", "doubt",
        "doubtful", "sceptical", "skeptical", "unrealistic", "aggressive", "overpriced",
        "expensive", "unclear", "vague", "risky", "concern", "concerned", "concerns",
        "worried", "worry", "fail", "failing", "delay", "delayed", "disappointed",
        "insufficient", "lacking", "misleading", "kharab", "bekaar", "ghatiya", "dhoka",
    }
    _INTENSIFIERS = {"very", "really", "extremely", "highly", "so", "too", "quite", "bahut"}
    _NEGATIONS = {"not", "no", "never", "hardly", "barely", "isn't", "aren't", "doesn't",
                  "don't", "won't", "cannot", "can't", "nahi", "nahin"}

    def classify(self, text: str) -> SentimentResult:
        tokens = re.findall(r"[\w']+", (text or "").lower())
        score = 0.0
        hits = 0
        for index, token in enumerate(tokens):
            weight = 0.0
            if token in self._POSITIVE:
                weight = 1.0
            elif token in self._NEGATIVE:
                weight = -1.0
            if weight == 0.0:
                continue
            hits += 1
            window = tokens[max(0, index - 3) : index]
            if any(w in self._NEGATIONS for w in window):
                weight = -weight * 0.9
            if any(w in self._INTENSIFIERS for w in window):
                weight *= 1.4
            score += weight

        # "but" reliably flips the emphasis to the clause after it.
        if " but " in f" {(text or '').lower()} " and score > 0:
            tail = (text or "").lower().split(" but ", 1)[1]
            if any(word in tail for word in self._NEGATIVE):
                score -= 1.2

        if hits == 0:
            return SentimentResult(label=str(Sentiment.NEUTRAL), score=0.5, model=self.model)
        normalised = score / max(hits, 1)
        confidence = round(min(0.5 + abs(normalised) * 0.45, 0.99), 4)
        if normalised >= 0.35:
            label = Sentiment.POSITIVE
        elif normalised <= -0.25:
            label = Sentiment.NEGATIVE
        else:
            label = Sentiment.NEUTRAL
        return SentimentResult(label=str(label), score=confidence, model=self.model)


def preprocess(text: str) -> str:
    """Normalise before classification: strip URLs, mentions and excess whitespace."""
    cleaned = re.sub(r"https?://\S+", " ", text or "")
    cleaned = re.sub(r"@\w+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:2000]


_provider: SentimentProvider | None = None


def get_provider() -> SentimentProvider:
    global _provider
    if _provider is None:
        if settings.sentiment_provider == "xlm-roberta":
            _provider = XLMRobertaProvider()
        else:
            _provider = MockSentimentProvider()
        logger.info("sentiment_provider_selected", provider=_provider.name)
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None


# --------------------------------------------------------------------------
# Aspect classification
# --------------------------------------------------------------------------
_ASPECT_KEYWORDS: dict[str, tuple[str, ...]] = {
    FeedbackAspect.FUNDING_TARGET: (
        "target", "goal", "amount", "raise", "raising", "funding", "crore", "lakh",
        "budget", "money", "ambitious", "aggressive",
    ),
    FeedbackAspect.EXECUTION_PLAN: (
        "execution", "plan", "timeline", "deliver", "delivery", "milestone", "roadmap",
        "schedule", "deadline", "logistics", "implement",
    ),
    FeedbackAspect.TEAM: (
        "team", "founder", "experience", "background", "credential", "track record",
        "who is", "expertise", "leadership",
    ),
    FeedbackAspect.SCALABILITY: (
        "scale", "scalable", "scalability", "expand", "growth", "replicate", "nationwide",
        "other states", "roll out", "rollout",
    ),
    FeedbackAspect.PRODUCT: (
        "product", "quality", "design", "durable", "build", "prototype", "material",
        "performance", "works well", "filter", "device",
    ),
    FeedbackAspect.IMPACT: (
        "impact", "community", "village", "people", "social", "benefit", "lives",
        "environment", "help", "families", "students", "farmers",
    ),
    FeedbackAspect.PRICING: ("price", "pricing", "cost", "expensive", "cheap", "affordable", "value"),
    FeedbackAspect.TECHNOLOGY: (
        "technology", "tech", "solar", "ai", "software", "hardware", "engineering",
        "innovation", "patent", "iot",
    ),
    FeedbackAspect.TRUST: (
        "trust", "transparent", "transparency", "scam", "genuine", "verify", "verified",
        "proof", "audit", "accountab", "legit",
    ),
}


def classify_aspects(text: str) -> list[str]:
    """Return every aspect the text plausibly touches, strongest first.

    Feedback rarely concerns exactly one thing; forcing a single label would
    discard the signal that makes the aspect chart useful.
    """
    lowered = (text or "").lower()
    scored: list[tuple[str, int]] = []
    for aspect, keywords in _ASPECT_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword in lowered)
        if hits:
            scored.append((str(aspect), hits))
    if not scored:
        return [str(FeedbackAspect.OTHER)]
    scored.sort(key=lambda item: item[1], reverse=True)
    return [aspect for aspect, _ in scored[:3]]


# --------------------------------------------------------------------------
# Service operations
# --------------------------------------------------------------------------
def analyze_feedback(db: Session, feedback: Feedback) -> Feedback:
    """Classify one feedback item. Failure is retryable, never silent."""
    try:
        result = get_provider().classify(feedback.text)
        aspects = classify_aspects(feedback.text)
        feedback.sentiment = result.label
        feedback.sentiment_score = result.score
        feedback.sentiment_model = result.model
        feedback.aspect = aspects[0]
        feedback.aspects = aspects
        feedback.analyzed_at = utcnow()
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=feedback.campaign_id,
            action=EventType.SENTIMENT_ANALYZED,
            actor_id=None,
            metadata={
                "feedback_id": feedback.id,
                "sentiment": result.label,
                "aspect": aspects[0],
                "model": result.model,
            },
        )
    except Exception as exc:
        logger.error("sentiment_failed", feedback_id=feedback.id, error=str(exc))
        feedback.sentiment = str(Sentiment.FAILED)
        db.flush()
    return feedback


def analyze_pending(db: Session, limit: int = 100) -> int:
    """Worker entry point: classify anything left PENDING or FAILED."""
    stmt = (
        select(Feedback)
        .where(Feedback.sentiment.in_([str(Sentiment.PENDING), str(Sentiment.FAILED)]))
        .order_by(Feedback.id)
        .limit(limit)
    )
    pending = list(db.execute(stmt).scalars().all())
    for item in pending:
        analyze_feedback(db, item)
    if pending:
        db.commit()
    return len(pending)


def feedback_count(db: Session, campaign_id: int) -> int:
    return int(
        db.execute(
            select(func.count(Feedback.id)).where(Feedback.campaign_id == campaign_id)
        ).scalar_one()
    )


def aggregate_campaign_sentiment(db: Session, campaign_id: int) -> CampaignSentimentStats:
    """Roll feedback up into the aggregate the dashboards and the LLM consume."""
    rows = list(
        db.execute(
            select(Feedback)
            .where(Feedback.campaign_id == campaign_id)
            .order_by(Feedback.id.desc())
        ).scalars().all()
    )
    stats = CampaignSentimentStats(feedback_count=len(rows))
    if not rows:
        return stats

    counts = {Sentiment.POSITIVE: 0, Sentiment.NEUTRAL: 0, Sentiment.NEGATIVE: 0}
    aspect_counts: dict[str, int] = {}
    rating_total = 0
    rating_distribution: dict[int, int] = {star: 0 for star in range(1, 6)}

    for row in rows:
        if row.sentiment in counts:
            counts[Sentiment(row.sentiment)] += 1
            stats.analyzed_count += 1
        rating_total += int(row.rating or 0)
        rating_distribution[int(row.rating or 0)] = (
            rating_distribution.get(int(row.rating or 0), 0) + 1
        )
        for aspect in row.aspects or ([row.aspect] if row.aspect else []):
            aspect_counts[aspect] = aspect_counts.get(aspect, 0) + 1

    analyzed = max(stats.analyzed_count, 1)
    stats.positive_percentage = round(counts[Sentiment.POSITIVE] / analyzed * 100, 1)
    stats.neutral_percentage = round(counts[Sentiment.NEUTRAL] / analyzed * 100, 1)
    stats.negative_percentage = round(
        100 - stats.positive_percentage - stats.neutral_percentage, 1
    )
    if stats.negative_percentage < 0:
        stats.negative_percentage = 0.0
    stats.average_rating = round(rating_total / len(rows), 2)
    stats.rating_distribution = rating_distribution

    total_mentions = sum(aspect_counts.values()) or 1
    stats.aspect_ranking = [
        (ASPECT_LABELS.get(aspect, aspect), round(count / total_mentions * 100, 1))
        for aspect, count in sorted(aspect_counts.items(), key=lambda kv: kv[1], reverse=True)
    ][:6]

    # A small, anonymised, opinion-bearing sample — never the whole corpus, and
    # never the author.
    negative = [r.text for r in rows if r.sentiment == Sentiment.NEGATIVE][:4]
    positive = [r.text for r in rows if r.sentiment == Sentiment.POSITIVE][:4]
    neutral = [r.text for r in rows if r.sentiment == Sentiment.NEUTRAL][:2]
    stats.sample_comments = [preprocess(text)[:280] for text in (negative + positive + neutral)][:10]
    return stats


def sentiment_summary_payload(stats: CampaignSentimentStats) -> dict[str, Any]:
    return {
        "feedback_count": stats.feedback_count,
        "analyzed_count": stats.analyzed_count,
        "average_rating": stats.average_rating,
        "positive_percentage": stats.positive_percentage,
        "neutral_percentage": stats.neutral_percentage,
        "negative_percentage": stats.negative_percentage,
        "aspect_distribution": [
            {"aspect": name, "percentage": pct} for name, pct in stats.aspect_ranking
        ],
        "rating_distribution": stats.rating_distribution,
    }
