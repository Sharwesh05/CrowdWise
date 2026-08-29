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
| `GemmaProvider` | `AI_PROVIDER=gemma` | Calls an OpenAI-compatible endpoint, retries once, recovers JSON from prose or code fences |
| `MockAnalysisProvider` | `AI_PROVIDER=mock` | Deterministic heuristic analyst |

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
