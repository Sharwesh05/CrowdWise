# AGENTS.md — CrowdWise Build Handbook

> **Purpose of this file:** this is the *resume document*. If a session ends, a new
> agent (or human) reads this file top-to-bottom and can continue the build with no
> other context. Keep the **Build Status** checklist in section 11 up to date after
> every meaningful chunk of work.

---

## 1. What we are building

**CrowdWise — AI-Powered Community Crowdfunding & Governance Platform**
Tagline: *Smarter Crowdfunding. Stronger Communities.*

CrowdWise is **not** "campaign → payment → money raised". It is a full lifecycle:

```
Creator → Register → Demo KYC → Application Fee → Campaign Submission
       → AI Campaign Analysis (NVIDIA NIM) → Admin Review → Approval → LIVE
       → Unique Campaign QR → Physical/Online Discovery → Campaign Page
       → Feedback / Rating → Razorpay Contribution → Server-side Verification
       → PostgreSQL Contribution Record → Blockchain Contribution Record
       → Sentiment (XLM-RoBERTa) + Aspect Analysis → LLM Community Intelligence
       → Deadline → TARGET_MET / TARGET_MISSED → Predefined Outcome
       → Contributor Governance → Blockchain Vote Record → Final Outcome
```

Philosophy: *crowdfunding should be a community participation and governance system,
not merely a payment system.*

---

## 2. Non-negotiable engineering rules

These rules shape every design decision in the repo. Do not violate them.

1. **Never trust frontend payment state.** Razorpay webhook + server-side signature
   verification is the only source of truth for money.
2. `campaigns.raised_amount` is incremented **only** inside the verified-payment
   transaction, never from a client callback.
3. **No sensitive data on-chain, ever.** No name, email, phone, PAN, Aadhaar,
   address, bank details, KYC payloads, or raw payment ids. On-chain we store
   hashes, amounts, timestamps, and opaque identifiers only.
4. **Blockchain failure must never corrupt payment state.** A verified payment stays
   verified; blockchain recording is a separate retryable state machine
   (`BLOCKCHAIN_PENDING → BLOCKCHAIN_RECORDED | BLOCKCHAIN_FAILED`).
5. **Blockchain is not a bank.** No Solidity function pretends to move INR. Refunds
   and settlements go through `PaymentService.refund()`.
6. **AI is decision support, not a verifier.** Every AI surface carries a disclaimer.
   Final campaign approval always requires a human admin.
7. **Every external integration has a demo/mock provider** selected by env var, so
   the whole demo runs locally with zero credentials.
8. **Explicit campaign state machine.** No endpoint may set an arbitrary status;
   transitions go through the state machine.
9. **Idempotency** on webhooks, contribution creation, blockchain recording, votes.
10. **Audit everything.** Every material state transition writes `audit_logs` and
    `campaign_events`.
11. **No secrets in source.** Everything from env; `.env.example` holds placeholders only.
12. **Never expose ORM models over the API.** Pydantic schemas only.

---

## 3. Technology stack (fixed — do not substitute)

| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript + Tailwind + shadcn-style components, React Hook Form, Zod, TanStack Query, Recharts, browser QR scanner |
| Backend | Python + FastAPI + SQLAlchemy 2.x + Alembic + Pydantic v2 |
| Database | PostgreSQL (SQLite only as a zero-infra dev/test fallback) |
| Payments | Razorpay (Test Mode) + webhook signature verification |
| LLM | NVIDIA NIM (provider-pluggable via env; any OpenAI-compatible endpoint) |
| Sentiment | XLM-RoBERTa multilingual (provider-pluggable via env) |
| Blockchain | Solidity + Hardhat + web3.py, local Hardhat node by default |
| Storage | S3-compatible abstraction (local disk driver for dev) |
| Infra | Docker + Docker Compose |

---

## 4. Repository layout

```
crowdwise/
├── frontend/            Next.js app
│   ├── app/             routes (App Router)
│   ├── components/      shared UI primitives + composites
│   ├── features/        feature-scoped components (campaign, governance, ...)
│   ├── hooks/           react hooks
│   ├── lib/             api client, formatting, auth helpers
│   ├── services/        typed API service functions
│   └── types/           shared TS types
│
├── backend/
│   ├── app/
│   │   ├── api/routes/   FastAPI routers (one per domain tag)
│   │   ├── core/         config, db, security, logging, errors, deps
│   │   ├── models/       SQLAlchemy models
│   │   ├── schemas/      Pydantic request/response schemas
│   │   ├── services/     business logic (the real brain of the app)
│   │   ├── repositories/ data access helpers
│   │   ├── middleware/   request id, logging, rate limit
│   │   ├── workers/      background jobs (sentiment, insights, chain sync, deadlines)
│   │   └── main.py
│   ├── alembic/          migrations
│   ├── tests/            pytest suite
│   └── seed.py           demo seed data
│
├── blockchain/
│   ├── contracts/CrowdWiseRegistry.sol
│   ├── scripts/deploy.ts
│   ├── test/
│   └── hardhat.config.ts
│
├── ai/                   prompt templates + model notes (shared, versioned)
├── infrastructure/docker/
├── docs/                 architecture.md, api.md, demo.md, deployment.md, runbook.md
├── docker-compose.yml
├── .env.example
└── README.md
```

**Rule:** business logic lives in `backend/app/services/`. Routers stay thin —
validate, authorize, delegate, serialize.

---

## 5. Service layer map (backend/app/services)

| Service | Responsibility |
|---|---|
| `auth_service` | register, login, password hashing, JWT in HTTP-only cookies |
| `kyc_service` | KYC facade + `DemoKYCProvider` (real provider pluggable) |
| `campaign_service` | CRUD, state transitions, health score |
| `campaign_state` | explicit allowed-transition map |
| `payment_service` | payment provider interface, Razorpay + demo impls, order creation, signature verification, webhook handling, refunds |
| `ai_service` | `CampaignAnalysisProvider` interface, `OpenAICompatibleProvider` (`NvidiaProvider`, `GemmaProvider`), `MockAnalysisProvider`, community insights |
| `sentiment_service` | `SentimentProvider` interface, `XLMRobertaProvider`, `MockSentimentProvider`, aspect classification |
| `blockchain_service` | web3.py contract calls, tx persistence, retry queue, mock chain |
| `governance_service` | eligibility, vote casting, tally, close, outcome |
| `storage_service` | storage interface, local disk + S3 impls |
| `qr_service` | qr token, PNG generation, campaign URL |
| `audit_service` | `audit_logs` and `campaign_events` writers |

---

## 6. Campaign state machine (authoritative)

```
DRAFT → KYC_PENDING → FEE_PENDING → ANALYSIS_PENDING → UNDER_REVIEW
      → APPROVED → LIVE → COMPLETED → TARGET_MET | TARGET_MISSED
      → GOVERNANCE → REFUND_PENDING | CONTINUED → CLOSED

UNDER_REVIEW → REJECTED          (admin reject)
UNDER_REVIEW → DRAFT             (admin request changes)
CONTINUED    → LIVE              (extended funding window)
```

Implemented in `backend/app/services/campaign_state.py` as an explicit allowed-transition
map. Invalid transitions raise `InvalidTransitionError` (HTTP 409).

---

## 7. Environment variables

Full list lives in `.env.example`. Key provider switches:

```
DEMO_MODE=true                # simulated KYC, seeded demo data, admin demo controls
AI_PROVIDER=mock|nvidia|gemma
SENTIMENT_PROVIDER=mock|xlm-roberta
PAYMENT_PROVIDER=demo|razorpay
BLOCKCHAIN_PROVIDER=mock|web3
STORAGE_PROVIDER=local|s3
```

Every provider interface must work with the `mock`/`demo`/`local` value and require
zero credentials. That is what makes the hackathon demo runnable offline.

---

## 8. How to run (target state)

```bash
cp .env.example .env
docker compose up --build              # postgres + backend + frontend + hardhat
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

Without Docker (this dev machine has none):

```bash
# backend
cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8000
# frontend
cd frontend && npm run dev
# blockchain
cd blockchain && npx hardhat node
cd blockchain && npx hardhat run scripts/deploy.ts --network localhost
```

Demo accounts (seeded, local only): `admin@example.com`, `creator@example.com`,
`contributor@example.com` — password documented in README for local dev only.

---

## 9. Conventions

- **Python:** snake_case, type hints everywhere, Pydantic v2 (`model_config`,
  `field_validator`), SQLAlchemy 2.0 style (`Mapped[...]`, `mapped_column`).
- **Money:** stored as `Numeric(14, 2)` rupees in the DB. Paise (`int`) exists only
  at the Razorpay boundary inside `payment_service`. Convert at the boundary, never
  in routers or the frontend.
- **IDs:** integer PKs internally; campaigns also carry a human `public_id`
  (`CMP-N2R6YW`, derived from the title) used in public URLs and as the
  on-chain campaign reference.
- **Errors:** services raise `AppError` subclasses; a FastAPI exception handler maps
  them to `{"error": {"code", "message", "details"}}`.
- **Frontend:** server components for static shells, client components for
  interactive state; all API calls go through `frontend/lib/api.ts`
  (`credentials: "include"`) and TanStack Query hooks in `frontend/hooks/`.
- **Never** leave a `TODO: implement X` in place of a feature. Ship the mock provider
  instead — it is real, working code.

---

## 10. Build order (phases)

1. Setup: docker, postgres, FastAPI skeleton, Next.js skeleton, auth
2. Users, roles, KYC, creator dashboard
3. Campaign lifecycle: create → application fee → AI analysis → admin approval
4. Public campaign, QR, discovery, contributor dashboard
5. Razorpay: order → checkout → webhook → verification → contribution
6. Blockchain: Hardhat, Solidity, contribution record, tx tracking
7. Feedback → sentiment → aspects → community insights → LLM summary
8. Governance: deadline → target missed → voting → chain result → refund/continue
9. Polish: dashboards, responsive UI, error/loading states, security, tests, docs

---

## 11. Build Status — UPDATE THIS AS YOU GO

Legend: `[ ]` not started · `[~]` in progress · `[x]` done and verified

### Phase 0 — Foundations
- [x] Monorepo directory skeleton
- [x] `AGENTS.md` (this file)
- [x] `docs/architecture.md`
- [x] Python venv + backend dependencies installed
- [x] `.env.example`
- [x] `docker-compose.yml` + Dockerfiles
- [x] `README.md`

### Phase 1 — Backend core
- [x] `core/config.py` settings
- [x] `core/db.py` session + engine
- [x] `core/security.py` hashing + JWT
- [x] `core/errors.py` + exception handlers
- [x] `middleware/` request id, structured logging, rate limit
- [x] SQLAlchemy models (all tables)
- [x] Alembic setup + initial migration
- [x] Auth routes + tests

### Phase 2 — Identity
- [x] KYC service + demo provider + routes
- [x] Role-based deps (`require_role`)

### Phase 3 — Campaign lifecycle
- [x] Campaign state machine
- [x] Campaign CRUD + application
- [x] Application fee order + verification
- [x] AI analysis service (mock + nvidia/gemma) + routes
- [x] Admin review routes (approve / reject / request-changes)

### Phase 4 — Public + QR
- [x] QR service + campaign QR endpoints
- [x] Public campaign endpoints + discovery / search / sort

### Phase 5 — Payments
- [x] Payment provider abstraction
- [x] Contribution order + verification + idempotency
- [x] Razorpay webhook handler

### Phase 6 — Blockchain
- [x] `CrowdWiseRegistry.sol`
- [x] Hardhat config, deploy script, contract tests
- [x] web3.py blockchain service + retry worker
- [x] Blockchain routes

### Phase 7 — Community intelligence
- [x] Feedback routes
- [x] Sentiment providers + aspect classification
- [x] Community insights (LLM) + caching

### Phase 8 — Governance
- [x] Outcome configuration
- [x] Deadline processing worker
- [x] Voting + eligibility + duplicate prevention
- [x] Governance close + outcome + chain record
- [x] Refund / continue states

### Phase 9 — Frontend
- [x] App shell, theme, UI primitives
- [x] Auth pages
- [x] Homepage / about / how-it-works
- [x] Campaign discovery + campaign page
- [x] Creator: dashboard, KYC, application, new campaign, campaign detail
- [x] Contributor: dashboard, contributions, votes, `/scan`
- [x] Admin: dashboard, campaigns list, review page, demo controls
- [x] Payment verification progress screen
- [x] Governance UI

> **Status: complete and verified.**
>
> | Suite | Result | Command |
> |---|---|---|
> | Backend | 82 passing | `cd backend && .venv/bin/python -m pytest tests/ -q` |
> | Smart contract | 22 passing | `cd blockchain && npx hardhat test` |
> | Frontend | 11 passing | `cd frontend && npx vitest run` |
> | Frontend build | 20 routes | `cd frontend && npm run build` |
> | Migration | applies cleanly | `cd backend && alembic upgrade head` |
> | Seed | 4 campaigns, 8 feedback | `cd backend && python seed.py` |
>
> Verified live: cookie + CSRF session flow, forged-signature rejection, genuine
> payment verification, blockchain anchoring (both simulated and real web3 against
> a deployed contract on a Hardhat node), duplicate-vote prevention.
>
> **Full demo executed end to end** against a live stack with
> `BLOCKCHAIN_PROVIDER=web3`: all 18 scenes green, 20/20 lifecycle events in the
> admin audit log, and the campaign's on-chain state read back directly from the
> contract's view functions (blocks 15-20: CAMPAIGN_REGISTERED, CONTRIBUTION,
> VOTING_OPENED, VOTE, VOTING_CLOSED, OUTCOME; tally refund=1 continue=0).
>
> **Operational note:** when resetting the database with `BLOCKCHAIN_PROVIDER=web3`,
> restart the Hardhat node too. Campaign references are derived deterministically
> from the public id, so a reused id against a chain that still holds the previous
> run reverts with `CampaignExists`. `seed.py --reset` now warns about this, and
> `register_campaign` treats an already-registered reference as benign.

### Phase 10 — Quality
- [x] Seed script
- [x] Backend tests (auth, lifecycle, payments, webhook idempotency, governance)
- [x] Blockchain tests
- [x] Frontend tests
- [x] `docs/api.md`, `docs/demo.md`, `docs/deployment.md`, `docs/runbook.md`
- [x] Final end-to-end demo verification

---

## 12. Known environment constraints (this machine)

- **No Docker installed.** Compose files are authored for the reviewer's machine;
  the local run path here uses the venv, `npm run dev`, and `npx hardhat node`.
- **No local PostgreSQL server.** `DATABASE_URL` defaults to Postgres for Docker, but
  `sqlite+pysqlite:///./crowdwise.db` is supported for zero-infra local runs and is
  what the test suite uses. All models stay Postgres-compatible (no SQLite-only types).
- Heavyweight ML wheels (`transformers`, `torch`) are not
  installed — `SENTIMENT_PROVIDER=mock` is the default, and the XLM-RoBERTa provider
  is implemented behind the same interface with a lazy import so it activates the
  moment the wheels are present.
