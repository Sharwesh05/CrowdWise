# Campaign analysis

Implementation: `backend/app/services/ai_service.py`
Prompt: `../prompts/campaign_analysis.md`

## Contract

Input is the creator-authored proposal only — title, category, target, window,
short description, problem, solution, expected impact, full description. No
contributor data and no personal data.

Output is validated into this shape before it is stored:

```json
{
  "feasibility_score": 0,
  "problem_clarity_score": 0,
  "impact_score": 0,
  "risk_score": 0,
  "summary": "",
  "strengths": [],
  "concerns": [],
  "recommendations": [],
  "questions_for_creator": [],
  "missing_information": []
}
```

Scores are clamped to 0-100. `risk_score` is the one where **higher is worse**.

## Providers

| Class | Selected by | Behaviour |
|---|---|---|
| `NvidiaProvider` | `AI_PROVIDER=nvidia` | NVIDIA NIM (hosted gateway or self-hosted) |
| `GemmaProvider` | `AI_PROVIDER=gemma` | Any other OpenAI-compatible endpoint (Ollama, vLLM, gateway) |
| `MockAnalysisProvider` | `AI_PROVIDER=mock` | Deterministic heuristic analyst |

Both LLM providers subclass `OpenAICompatibleProvider`. It sends **model and
messages only** — no `temperature`, `max_tokens` or `response_format` unless the
env explicitly asks for them. Across a catalogue as wide as NIM's, every extra
field is one more thing a given model can reject or mishandle; a `max_tokens`
sized for a plain instruct model truncates a reasoning model mid-thought, before
it emits any JSON.

`NVIDIA_JSON_MODE=auto` (the default) asks plainly first and retries with
`response_format` only if the reply could not be parsed. `on` always sends it,
`off` never does.

The client also strips `<think>` blocks, recovers JSON from prose or code fences,
raises a named error on an empty/truncated reply, and reports a 404 as "model not
available on this account" rather than masking it. A provider that cannot be
constructed (missing key, bad URL) logs and falls back to the heuristic analyst
instead of crashing the app.

## The heuristic analyst

`MockAnalysisProvider` is not a canned response. It scores the proposal on
observable properties: specificity, presence of quantities, plan markers
(phases, milestones, partners, timelines), team markers, impact markers, scale
markers, budget-to-ambition ratio and funding-window length. A vague proposal
scores measurably worse than a detailed one, which is what makes the offline
demo worth watching.

## Failure handling

A model failure never blocks a submission. The record is written with the
fallback result, `status=DEGRADED`, and the error string — and the admin review
panel flags it so scores are read as indicative.
