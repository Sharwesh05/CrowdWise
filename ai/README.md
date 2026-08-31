# CrowdWise AI

Prompt templates and model notes, versioned with the code that uses them.

## Layout

- `prompts/campaign_analysis.md` — campaign proposal analysis
- `prompts/community_insights.md` — community intelligence summary

Both are loaded at runtime by `backend/app/services/ai_service.py`, which parses
the `## SYSTEM` and `## USER` sections. Editing a prompt does not require a code
change or a redeploy of the model.

## Two AI surfaces, deliberately separate

**Campaign analysis** runs once per submission on the creator-authored proposal
only. Output is validated against a Pydantic schema; the model never defines its
own structure. On failure it retries once, then falls back to a deterministic
heuristic analyst and marks the record `DEGRADED`.

**Community intelligence** never sees individual comments one at a time. Each
comment goes to the cheap multilingual classifier when it is written; only
aggregated statistics and a small anonymised sample reach the language model, in
a single call per campaign. This is both the cost control and the privacy
control.

## Models

| Purpose | Model | Provider switch |
|---|---|---|
| Analysis and summarisation | Any NVIDIA NIM chat model (default `nvidia/nemotron-3-super-120b-a12b`) | `AI_PROVIDER=nvidia` |
| Analysis and summarisation | Gemma, or any other OpenAI-compatible endpoint | `AI_PROVIDER=gemma` |
| Sentiment | `cardiffnlp/twitter-xlm-roberta-base-sentiment` | `SENTIMENT_PROVIDER=xlm-roberta` |

Both LLM switches share one client (`OpenAICompatibleProvider`); they differ only
in endpoint, key, model and JSON-mode handling. The prompts are provider-neutral,
so swapping models is an env change.

With the `mock` defaults, a heuristic analyst and a lexicon-and-negation
classifier run instead. Both read the actual text — two different campaigns get
two genuinely different analyses — so the offline demo is honest rather than
canned.

## Rules

1. No personal data reaches a model. Names, emails, phone numbers, KYC fields and
   raw payment identifiers stay in the database.
2. Model output is always validated before it is stored.
3. AI is decision support. It never approves a campaign; a human admin does.
4. Every AI surface in the UI carries the disclaimer.
