# CrowdWise — Demo Script

The full lifecycle, start to finish, in about eight minutes. Every step below
works against a freshly seeded local stack with **zero credentials**.

---

## Before you start

```bash
cp .env.example .env
docker compose up --build
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

Or without Docker:

```bash
cd backend && alembic upgrade head && python seed.py && uvicorn app.main:app --port 8000
cd frontend && npm run dev
```

Open two browser profiles side by side (or a laptop and a phone):

- **Window A** — the creator and admin
- **Window B** — the contributor (this is the one that scans the QR)

Accounts (`Demo@12345` for all): `admin@example.com`, `creator@example.com`,
`contributor@example.com`.

> **Tip:** the seed already contains a fully populated campaign and an open
> governance round. Campaign ids are derived from the title (`CMP-N2R6YW`), so
> `seed.py` prints the id of every campaign it creates — keep that output on
> screen. If you are short on time, skip to Scene 8 using the funded campaign, or
> to Scene 16 using the one with the open governance round.

> **Re-running the demo with `BLOCKCHAIN_PROVIDER=web3`:** restart the Hardhat
> node whenever you reset the database. Campaign references are derived
> deterministically from the public id, and the public id is derived from the
> title, so re-seeding the same titles against a chain that still holds the
> previous run reverts with `CampaignExists` — the contract
> correctly refusing to register the same reference twice. Restarting the node
> clears its in-memory state. With the default `BLOCKCHAIN_PROVIDER=mock` this
> does not arise.

---

## Scene 1 — Creator registration

**Window A** → `/register` → choose *I want to run a campaign*.

Register as a new creator. You land on the KYC page, because the lifecycle does
not let you go anywhere else first.

> **Say:** "A campaign cannot exist until we know who is asking."

---

## Scene 2 — Demo KYC

`/creator/kyc`. The **DEMO KYC MODE** badge is visible throughout.

Fill in test values only:

| Field | Value |
|---|---|
| Full name | Asha Menon |
| Date of birth | 1990-04-12 |
| PAN (demo) | `ABCDE1234F` |
| Address | 12 Demo Street, Test Nagar, Bengaluru 560001 |
| Bank account (demo) | `000123456789` |
| IFSC (demo) | `DEMO0001234` |

Submit. The status steps through **SUBMITTED → PROCESSING → VERIFIED** — the same
states a real provider would report.

> **Say:** "Simulated, but the state machine and the audit trail are real. Swapping
> in a licensed vendor is one class behind an interface."

---

## Scene 3 — Application fee

Create the campaign first (Scene 4), then return here — or use the seeded creator.

`/creator/campaigns/[id]` → **Lifecycle** tab → **Submit for review** → **Pay ₹500**.

With `PAYMENT_PROVIDER=demo` the fee is signed and verified locally. With Razorpay
test keys the real checkout sheet opens.

> **Say:** "The application does not advance because the browser said the payment
> worked. It advances because the server verified an HMAC signature."

---

## Scene 4 — Create the campaign

`/creator/campaigns/new`:

| Field | Value |
|---|---|
| Title | Solar Water Purifier for Rural Schools |
| Category | Environment |
| Target | `1000000` (₹10,00,000) |
| Minimum contribution | `500` |
| Deadline | 45 days out |
| Outcome rule | Contributors vote — refund or continue |

Write a real problem, solution and description. The analysis rewards specifics —
budget lines, partners, timelines — so a vague proposal visibly scores worse.

---

## Scene 5 — AI analysis

**Lifecycle** tab → **Run AI analysis**.

Scores appear for feasibility, problem clarity, impact and execution risk, with
strengths, concerns, recommendations and questions for the reviewer.

> **Say:** "This is decision support. Note the disclaimer — it travels with every
> AI surface in the product, and nothing here approves anything."

---

## Scene 6 — Admin review

**Window A** → sign out → sign in as `admin@example.com` → `/admin/dashboard` →
**Review pending**.

The review page shows three gate cards — identity verification, ₹500 fee,
AI analysis — plus risk indicators, the full proposal, and the questions worth
asking. Click **Approve and publish**.

> **Say:** "A person approves. That is a deliberate constraint, not a missing feature."

---

## Scene 7 — The QR

Back as the creator: `/creator/campaigns/[id]` → **QR & sharing**.

The campaign now has a unique QR, a copyable URL, a PNG download and a
print-friendly page.

> **Say:** "Every approved campaign gets one. It works on a poster, a stall, a
> slide or a social post — and it carries a link, not money."

---

## Scene 8 — Contributor discovery

**Window B** (or your phone) → `/scan` → **Start camera** → scan the QR.

No camera? The same page accepts an uploaded QR image or a pasted link — the demo
never depends on hardware.

The campaign page opens: funding progress, backers, deadline, health score, AI
analysis, community sentiment, and blockchain verification.

---

## Scene 9 — Contribute

Sign in as `contributor@example.com` → **Contribute** → ₹500 → **Continue to payment**.

- `PAYMENT_PROVIDER=demo`: click **Complete demo payment**
- `PAYMENT_PROVIDER=razorpay`: the Razorpay test sheet opens (card `4111 1111 1111 1111`, any future expiry, any CVV)

---

## Scene 10 — Payment verification

Watch the dialog. It does **not** say "Payment successful". It shows:

```
✓ Payment received
✓ Payment verified on the server
✓ Contribution recorded
◌ Blockchain record confirmed
```

Each tick is a distinct server-side fact, polled from `/api/payments/{id}/progress`.

> **Say:** "This is the architecture made visible. Most products collapse all four
> of these into one green tick."

---

## Scene 11 — Blockchain

The dialog shows the transaction hash. The **Verification** tab on the campaign
page lists every anchored record with its type, hash and block number.

> **Say:** "Hashes, amounts and timestamps only. No name, no email, no payment id
> — a salted hash of the payment reference is all that goes on chain."

---

## Scene 12 — Feedback

Still as the contributor → **Feedback** → 4 stars →

> *"Good social impact, but the funding target seems aggressive."*

---

## Scene 13 — Sentiment and aspect

**Community** tab. The comment now carries a sentiment label and an aspect tag,
and the distribution charts update. The "but" clause is handled — that phrasing is
where naive classifiers usually go wrong.

> **Say:** "Sentiment alone is not enough. Knowing that the concern is about the
> *funding target* rather than the *team* is what the creator can act on."

---

## Scene 14 — AI community intelligence

**AI insights** tab → **Refresh**.

A single summary of what the community collectively thinks, with positive themes,
top concerns, recommendations and a risk signal.

> **Say:** "Five hundred comments do not go to the language model one at a time.
> They go to the cheap classifier, get aggregated, and the model sees the
> aggregate plus a small anonymised sample. One call, no personal data."

---

## Scene 15 — End the campaign

**Window A** as admin → `/admin/dashboard` → **Demo controls** →
*Simulate deadline reached* → the id of the seeded under-funded campaign (
or your own).

The campaign completes below target and moves to **GOVERNANCE**.

> **Say:** "The system reports the arithmetic. It does not invent an outcome —
> what happens next comes from rules fixed before funding opened."

---

## Scene 16 — Governance

**Window B** → the campaign page. The governance panel shows the shortfall, the
eligible voter count, the participation rate, and the two predefined options:
**Refund** and **Continue**.

---

## Scene 17 — Vote

Vote as the contributor. Then try to vote again — rejected. Sign in as a user who
never contributed and try — rejected.

> **Say:** "One vote per contributor, enforced by a database constraint *and* by
> the contract. Not by a hopeful if-statement."

---

## Scene 18 — Outcome on chain

Admin → **Close voting and apply the outcome**.

The winning option is applied: **REFUND** moves the campaign to `REFUND_PENDING`
and flags contributions for refund through the payment provider; **CONTINUE**
extends the deadline and reopens funding. Either way, the decision is anchored.

> **Close with:** "The blockchain recorded the decision. The rupees move through
> Razorpay, because that is the only thing that can legally move rupees. That
> boundary is the whole point."

---

## Fast paths

| To show | Do this |
|---|---|
| A funded campaign with sentiment | Open the funded campaign from the seed output |
| An open governance round | Open the campaign the seed reports as `GOVERNANCE` |
| The admin review queue | The seed leaves one campaign `PENDING_REVIEW` |
| Chain-failure handling | Stop the Hardhat node, contribute, watch it stay verified with a pending anchor, then retry |
| Webhook idempotency | `cd backend && pytest tests/test_payments.py -q` |

---

## Demo controls reference

Admin-only, and refused entirely when `DEMO_MODE=false`.

| Action | What it does |
|---|---|
| Complete KYC | Settles a user's verification immediately |
| Trigger AI analysis | Runs analysis and advances to review |
| Simulate deadline | Sets the deadline to now and completes the campaign |
| Mark target missed | Completes the campaign and asserts it fell short |
| Open / close governance | Opens or closes a voting round and applies the outcome |
| Retry blockchain | Re-attempts failed anchors for a campaign |
| Refresh insights | Classifies pending feedback and regenerates the summary |
| Process refunds | Initiates refunds through the payment provider |

These compress *time*. None of them fabricates a payment or bypasses a signature
check.
