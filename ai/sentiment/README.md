# Sentiment and aspect analysis

Implementation: `backend/app/services/sentiment_service.py`

## Pipeline

```
feedback → preprocess → classifier → POSITIVE | NEUTRAL | NEGATIVE + confidence
                     → aspect classification (multi-label)
                     → database
                     → aggregation → community insights
```

Classification happens **when feedback is created**, in a background task —
never on a dashboard render.

## Providers

| Class | Selected by | Behaviour |
|---|---|---|
| `XLMRobertaProvider` | `SENTIMENT_PROVIDER=xlm-roberta` | `cardiffnlp/twitter-xlm-roberta-base-sentiment`, lazy-loaded once |
| `MockSentimentProvider` | `SENTIMENT_PROVIDER=mock` | Lexicon classifier with negation and intensifier handling |

The lexicon provider handles negation windows ("not good"), intensifiers ("very
useful"), the `but` pivot that flips emphasis to the second clause, and a small
Hindi/Hinglish vocabulary — so the multilingual story is real in the demo rather
than decorative.

## Aspects

Feedback rarely concerns exactly one thing, so aspects are multi-label, ranked by
keyword strength, capped at three:

`FUNDING_TARGET` · `EXECUTION_PLAN` · `TEAM` · `SCALABILITY` · `PRODUCT` ·
`IMPACT` · `PRICING` · `TECHNOLOGY` · `TRUST` · `OTHER`

This is the difference between "12% negative" and "the concern is the funding
target, not the team" — only the second is actionable for a creator.

## Aggregation

`aggregate_campaign_sentiment()` produces the distribution, the average rating,
the rating histogram, the ranked aspect distribution, and a small anonymised
sample of opinion-bearing comments. That aggregate — never the raw corpus, never
an author — is what reaches the language model.
