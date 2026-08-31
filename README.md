# CrowdWise

**AI-Powered Community Crowdfunding & Governance Platform**

> Smarter Crowdfunding. Stronger Communities.

CrowdWise transforms crowdfunding from a simple funding transaction into a
community-driven lifecycle: creators are verified and AI-evaluated, contributors
discover campaigns through physical or online QR interactions, payments are
verified through Razorpay, community feedback is analysed with AI, important
events are anchored on blockchain, and contributors participate in predefined
campaign outcomes.

---

## What this is

Most crowdfunding platforms model the domain as `campaign → payment → money raised`.
CrowdWise models it as a governed lifecycle:

```
Creator → Register → Demo KYC → ₹500 Application Fee → Campaign Submission
       → AI Campaign Analysis → Admin Review → Approval → LIVE
       → Unique Campaign QR → Physical / Online Discovery → Campaign Page
       → Feedback / Rating → Razorpay Contribution → Server-side Verification
       → PostgreSQL Contribution Record → Blockchain Contribution Record
       → Sentiment Analysis + Aspect Analysis → AI Community Intelligence
       → Deadline → TARGET_MET / TARGET_MISSED → Predefined Outcome
       → Contributor Governance → Blockchain Vote Record → Final Outcome
```

Four boundaries hold the design together, and the code enforces all four:

| Concern | System of record | Never the system of record |
|---|---|---|
| Money (INR) | Razorpay + settlement infrastructure | blockchain, frontend, QR |
| Application state | PostgreSQL | blockchain |
| Tamper-evidence | Blockchain (EVM) | PostgreSQL |
| Approval decisions | A human admin | AI |

---

## Architecture

```
Next.js frontend
      │  (HTTP-only cookie session + CSRF token)
      ▼
FastAPI  ──►  Service layer  ──►  PostgreSQL
      │            │
      │            ├──► Razorpay        (orders, checkout, signed webhooks)
      │            ├──► NVIDIA NIM / LLM (campaign analysis, community summary)
      │            ├──► XLM-RoBERTa     (multilingual sentiment)
      │            ├──► EVM chain       (CrowdWiseRegistry.sol via web3.py)
      │            └──► Object storage  (local disk / S3 / R2)
      │
      └──► Background worker (sentiment, insights, deadlines, chain retries)
```

Full detail, including Mermaid diagrams for every layer:
[`docs/architecture.md`](docs/architecture.md).

---

## Requirements

- Docker + Docker Compose *(recommended)*, or
- Python 3.11+ · Node.js 20+ · PostgreSQL 16 *(SQLite works for a zero-infra run)*

No Razorpay keys, no LLM endpoint, no chain node and no cloud storage are needed
to run the full demo. Every integration ships with a working demo provider.

---

## Installation

### Option A — Docker (one command)

```bash
git clone <repo> crowdwise && cd crowdwise
cp .env.example .env

docker compose up --build

# In a second terminal, once the stack is healthy:
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

- Frontend: <http://localhost:3000>
- API + docs: <http://localhost:8000/docs>
- Hardhat node: <http://localhost:8545>

### Option B — Local processes

```bash
cp .env.example .env

# --- backend ---
cd backend
python -m venv .venv
source .venv/bin/activate && pip install -r requirements.txt

# Zero-infra database (or point DATABASE_URL at Postgres)
export DATABASE_URL="sqlite+pysqlite:///./crowdwise.db"

alembic upgrade head
python seed.py
uvicorn app.main:app --reload --port 8000

# --- frontend (new terminal) ---
cd frontend
npm install
npm run dev

# --- blockchain (optional, new terminal) ---
cd blockchain
npm install
npx hardhat node
npx hardhat run scripts/deploy.ts --network localhost
```

---

## Environment variables

Everything lives in `.env` (see [`.env.example`](.env.example) for the full list
with placeholders). The switches that matter most:

| Variable | Values | Effect |
|---|---|---|
| `DEMO_MODE` | `true` / `false` | Simulated KYC, admin demo controls, seeded data |
| `PAYMENT_PROVIDER` | `demo` / `razorpay` | Credential-free signed payments, or real Razorpay |
| `AI_PROVIDER` | `mock` / `nvidia` / `gemma` | Heuristic analyst, NVIDIA NIM, or any OpenAI-compatible endpoint |
| `SENTIMENT_PROVIDER` | `mock` / `xlm-roberta` | Lexicon classifier, or the transformer model |
| `BLOCKCHAIN_PROVIDER` | `mock` / `web3` | Simulated ledger, or a real EVM chain |
| `STORAGE_PROVIDER` | `local` / `s3` | Local disk, or S3 / R2 / Supabase |

**Never commit `.env`.** No secret appears anywhere in source; `.env.example`
contains placeholders only.

---

## Database migrations

```bash
cd backend
alembic upgrade head                                  # apply
alembic revision --autogenerate -m "describe change"  # create after a model change
alembic downgrade -1                                  # roll back one
```

Application startup never alters the schema — migrations are always explicit.

---

## Blockchain

```bash
cd blockchain
npm install
npx hardhat compile
npx hardhat test                                      # 22 contract tests
npx hardhat node                                      # local chain on :8545
npx hardhat run scripts/deploy.ts --network localhost
```

The deploy script prints the values to put in `.env`:

```
BLOCKCHAIN_PROVIDER=web3
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
BLOCKCHAIN_RPC_URL=http://localhost:8545
BLOCKCHAIN_PRIVATE_KEY=<hardhat account #0 key — local only>
```

With `BLOCKCHAIN_PROVIDER=mock` (the default) the backend uses an in-process
simulated ledger, clearly labelled as simulated everywhere it appears in the UI.

---

## AI configuration

```
# NVIDIA NIM (hosted) — key from https://build.nvidia.com
AI_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b   # verify against GET /v1/models
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1   # or a self-hosted NIM container

# Or any other OpenAI-compatible endpoint
# AI_PROVIDER=gemma
# GEMMA_BASE_URL=http://localhost:11434/v1   # Ollama, vLLM, or a hosted gateway
# GEMMA_MODEL=gemma3:4b
# GEMMA_API_KEY=                             # only if the endpoint requires one

SENTIMENT_PROVIDER=xlm-roberta
SENTIMENT_MODEL=cardiffnlp/twitter-xlm-roberta-base-sentiment
```

The XLM-RoBERTa provider needs `transformers` and `torch`; it is lazy-imported,
so the rest of the stack runs without those wheels. With the defaults
(`mock`), a heuristic analyst and a lexicon-and-negation classifier run instead —
both read the actual text, so different campaigns get genuinely different results.

---

## Razorpay test configuration

```
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
RAZORPAY_KEY_SECRET=<test key secret>
RAZORPAY_WEBHOOK_SECRET=<webhook secret>
NEXT_PUBLIC_RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxxx
```

In the Razorpay dashboard, point a webhook at `POST /api/webhooks/razorpay` and
subscribe to `payment.captured`, `payment.failed` and `order.paid`. For local
testing, tunnel the endpoint (`ngrok http 8000`) so Razorpay can reach it.

With `PAYMENT_PROVIDER=demo` the checkout sheet is replaced by a local simulator
that produces a **genuine HMAC signature** and goes through the same verification
code path — a wrong signature is rejected in demo mode exactly as it would be live.

---

## Demo accounts

Created by `python seed.py`. **Local development only.**

| Role | Email | Password |
|---|---|---|
| Admin | `admin@example.com` | `Demo@12345` |
| Creator | `creator@example.com` | `Demo@12345` |
| Contributor | `contributor@example.com` | `Demo@12345` |

Also seeded: `creator2@example.com`, `contributor2@example.com`,
`contributor3@example.com` (same password). The seed creates four campaigns —
one live and well funded, one live and early, one awaiting review, and one in an
open governance round — plus feedback, classified sentiment, contributions and
on-chain records. Every seeded record is marked `DEMO`.

---

## Running tests

```bash
# Backend — 82 tests: auth, lifecycle, payments, webhook idempotency,
# sentiment, governance, privacy, chain-failure isolation
cd backend && pytest tests/ -q

# Smart contract — 22 tests
cd blockchain && npx hardhat test

# Frontend — 11 tests
cd frontend && npx vitest run
```

---

## Demo flow

The full 18-scene script is in [`docs/demo.md`](docs/demo.md), and the commands,
provider switches and known failure modes are in
[`docs/runbook.md`](docs/runbook.md). The short version:

1. Register a creator, complete demo KYC → **VERIFIED**
2. Pay the ₹500 application fee → verified server-side
3. Create the *Solar Water Purifier* campaign, run AI analysis
4. Sign in as admin, review the gates, approve → campaign goes **LIVE** with a QR
5. Scan the QR from a phone or another browser
6. Contribute ₹500 → watch payment received → verified → contribution recorded →
   blockchain confirmed
7. Leave feedback → sentiment and aspect appear → AI community summary updates
8. Use a demo control to simulate the deadline with the target missed
9. Governance opens → contributors vote refund or continue → the vote is anchored
10. Close the round → the outcome is applied and recorded on chain

---

## Project structure

```
crowdwise/
├── frontend/           Next.js 14 app router, TypeScript, Tailwind, TanStack Query
├── backend/            FastAPI, SQLAlchemy 2, Alembic, Pydantic v2
│   ├── app/api/        routers + serializers
│   ├── app/core/       config, db, security, errors, logging, deps, enums
│   ├── app/models/     16 tables
│   ├── app/services/   the business logic
│   ├── app/workers/    background jobs
│   ├── alembic/        migrations
│   ├── tests/          pytest suite
│   └── seed.py         demo data
├── blockchain/         Solidity + Hardhat + TypeChain
├── ai/prompts/         versioned prompt templates
├── infrastructure/     Dockerfiles
├── docs/               architecture, api, demo, deployment, runbook
└── docker-compose.yml
```

---

## Production considerations

Before this becomes a real product, the following need real work:

- **KYC.** The demo provider must be replaced with a licensed vendor behind the
  existing `KYCProvider` interface. Nothing else has to change.
- **Payouts.** Contributions are recorded, but disbursement to creators needs a
  Razorpay Route / linked-account flow behind `PaymentProvider`, plus the
  compliance work that comes with holding other people's money.
- **Refunds at scale.** `PaymentService.refund()` is real but sequential; a
  governance round with thousands of contributors needs a queued, resumable job.
- **Rate limiting.** The in-process limiter is per-node. Multi-node deployment
  needs Redis.
- **Background jobs.** The threaded worker is deliberate for a single node.
  Celery or RQ becomes worthwhile once jobs must survive a restart.
- **Secrets.** Move from `.env` to a managed secret store; rotate the chain
  recorder key and the `CHAIN_HASH_SALT` independently.
- **Observability.** Structured logs exist; ship them somewhere, and add tracing
  across the payment → contribution → anchor path.
- **Legal.** Crowdfunding in India carries real regulatory obligations around
  fundraising, refunds and tax. That is a legal question, not an engineering one.

### Known limitations

- The `mock` AI and sentiment providers are heuristics, not language models.
  They read the real text and produce differentiated output, but they are not a
  substitute for Gemma or XLM-RoBERTa in production.
- The simulated blockchain ledger lives in process memory and is cleared on
  restart. Use `BLOCKCHAIN_PROVIDER=web3` for persistence.
- Governance supports one round per campaign. A second round would need the
  `governance_round` column (already present) to be surfaced through the API.
- Campaign cover images are URLs; there is no image pipeline or CDN.
- The frontend is not internationalised, though the sentiment model is
  multilingual and the classifier handles Hindi/Hinglish input.

---

## Licence

Built as a hackathon MVP.

**CrowdWise — Smarter Crowdfunding. Stronger Communities.**
