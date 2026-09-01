# CrowdWise — API Reference

Interactive documentation is generated automatically:

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- OpenAPI JSON: <http://localhost:8000/openapi.json>

This document covers the conventions and the parts of the contract that the
generated docs cannot express.

---

## Conventions

### Authentication

Sessions are JWTs in **HTTP-only cookies**, so JavaScript can never read them.

| Cookie | Readable by JS | Purpose |
|---|---|---|
| `cw_access` | No | Access token |
| `cw_refresh` | No | Refresh token |
| `cw_csrf` | Yes | Double-submit CSRF token |

Every browser request must send `credentials: "include"`. Every state-changing
request must echo the CSRF cookie in an `X-CSRF-Token` header.

API clients and tests may instead send `Authorization: Bearer <token>`. An
explicit bearer header takes precedence over the cookie and is exempt from the
CSRF check — it cannot be forged by a browser riding someone's session.

### Error envelope

Every error, from every endpoint:

```json
{
  "error": {
    "code": "conflict",
    "message": "You have already voted in this governance round.",
    "details": { "optional": "structured context" }
  }
}
```

| Status | Code | Meaning |
|---|---|---|
| 400 | `payment_verification_failed` | Signature check failed — nothing was recorded |
| 401 | `unauthenticated` | No or expired session |
| 403 | `permission_denied` | Wrong role, not your resource, or missing CSRF token |
| 404 | `not_found` | Absent, or not public yet |
| 409 | `conflict` / `invalid_state_transition` | The lifecycle forbids this right now |
| 422 | `validation_error` | Request body failed validation |
| 429 | `rate_limited` | Too many requests; `Retry-After` header is set |
| 502 | `external_service_error` | An upstream integration failed |

### Pagination

List endpoints return `{ items, total, limit, offset }` and accept `limit` and
`offset`. Feedback and contributions are always paginated — a campaign with 500
comments is never returned in one response.

### Money

All amounts are **rupee strings** with two decimals (`"500.00"`). Paise integers
appear only in `amount_paise` on order responses, because that is what the
Razorpay checkout sheet requires.

---

## Endpoints

### Auth

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/auth/register` | Role must be `CREATOR` or `CONTRIBUTOR`; admins are provisioned separately |
| `POST` | `/api/auth/login` | Sets the session cookies, returns the CSRF token |
| `POST` | `/api/auth/logout` | Clears cookies |
| `GET` | `/api/auth/me` | Current user plus derived KYC state |
| `POST` | `/api/auth/refresh` | Exchanges the refresh cookie for a new session |
| `POST` | `/api/auth/change-password` | Requires the current password |

### KYC

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/kyc/submit` | Demo only; test values are validated for shape, not identity |
| `GET` | `/api/kyc/status` | `NOT_STARTED` → `SUBMITTED` → `PROCESSING` → `VERIFIED` |
| `POST` | `/api/kyc/complete` | Forces settlement (the demo provider resolves instantly) |

### Campaigns (creator)

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/campaigns` | Creates a `DRAFT` plus its application and outcome rules |
| `GET` | `/api/campaigns/my` | The creator's campaigns |
| `GET` | `/api/campaigns/{id}` | Owner view: application, review notes, timeline |
| `PATCH` | `/api/campaigns/{id}` | Editable while `DRAFT`, `KYC_PENDING`, `FEE_PENDING` or `UNDER_REVIEW`; the response's `editable` flag is the authority. Editing under review flags the analysis as stale on the review panel |
| `POST` | `/api/campaigns/{id}/submit` | `DRAFT → KYC_PENDING → FEE_PENDING`; **409 unless KYC is verified** |
| `POST` | `/api/campaigns/{id}/application-fee/order` | Creates the application fee order |
| `GET` | `/api/campaigns/{id}/application-fee/status` | Fee and campaign status |
| `POST` | `/api/campaigns/{id}/analyze` | Runs analysis, then `ANALYSIS_PENDING → UNDER_REVIEW` |
| `GET` | `/api/campaigns/{id}/analysis` | Latest analysis |
| `POST` | `/api/campaigns/{id}/documents` | Upload; `visibility` is `SHARED` or `AI_ONLY` (default). MIME allowlist, size cap, randomised storage key |
| `GET` | `/api/campaigns/{id}/documents` | Both tiers, with whether the AI could read each file |
| `DELETE` | `/api/campaigns/{id}/documents/{doc_id}` | Removes the record and the stored bytes |
| `GET` | `/api/campaigns/{id}/documents/{doc_id}/download` | Authenticated. Creator/admin read any tier; another signed-in user reads `SHARED` only, and only once the campaign is public |
| `POST` | `/api/campaigns/{id}/cover-image` | Replaces the cover image; images only, stored under `covers/` |
| `GET` | `/api/campaigns/{id}/qr` | QR token, URL and data URI (owner only) |

### Public

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/public/campaigns` | `search`, `category`, `status`, `sort`, `limit`, `offset` |
| `GET` | `/api/public/campaigns/{public_id}` | Full public page projection |
| `GET` | `/api/public/campaigns/{public_id}/documents` | Counts for everyone; the `SHARED` files only when signed in |
| `GET` | `/api/public/campaigns/{public_id}/qr.png` | Downloadable PNG |
| `GET` | `/api/public/campaigns/{public_id}/feedback` | Paginated |
| `GET` | `/api/public/campaigns/{public_id}/contributions` | Backers, first name and initial only |
| `GET` | `/api/public/campaigns/{public_id}/blockchain` | Anchored records |
| `GET` | `/api/public/scan/{qr_token}` | Resolves a scanned token to its campaign |
| `GET` | `/api/public/stats` | Observed platform totals |

`sort` accepts `trending`, `newest`, `progress`, `most_supported`, `ending_soon`.
No engagement metric is fabricated — every sort is over stored values.

### Payments and contributions

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/campaigns/{public_id}/contribute` | Creates an order. **No money state changes here.** |
| `POST` | `/api/payments/verify` | Verifies the checkout callback signature |
| `POST` | `/api/payments/{id}/simulate` | Demo provider only; produces a real signature |
| `GET` | `/api/payments/{id}` | Payment record |
| `GET` | `/api/payments/{id}/progress` | Drives the multi-step verification screen |
| `POST` | `/api/webhooks/razorpay` | Signed webhook; idempotent; CSRF-exempt |
| `GET` | `/api/contributions/my` | The caller's contributions |
| `GET` | `/api/contributions/{id}` | One contribution with payment and chain record |

**The payment contract, precisely:**

1. `contribute` creates a `Payment` row with status `CREATED`. Nothing else moves.
2. `verify` checks `HMAC_SHA256(order_id + "|" + payment_id, key_secret)`. An
   invalid signature marks the payment `FAILED` (and persists that) and returns 400.
3. The signed webhook does the same work independently and sets `webhook_verified`.
4. Whichever arrives first creates the `Contribution` and increments
   `raised_amount`, inside one transaction. The second is a no-op — enforced by a
   unique constraint on `contributions.payment_id`, not by application logic.
5. Blockchain anchoring is dispatched separately and may fail without affecting
   any of the above.

### Feedback and community AI

| Method | Path | Notes |
|---|---|---|
| `POST` | `/api/campaigns/{public_id}/feedback` | Auth required; one per contributor per campaign |
| `GET` | `/api/campaigns/{public_id}/feedback` | Filter by `sentiment` or `aspect` |
| `GET` | `/api/campaigns/{public_id}/sentiment` | Aggregated distribution and aspects |
| `GET` | `/api/campaigns/{public_id}/community-insights` | Cached summary; 404 until feedback exists |
| `POST` | `/api/campaigns/{public_id}/community-insights/refresh` | Forces regeneration |

Sentiment is classified in a background task when feedback is created, never on
read. Insights are cached until `COMMUNITY_INSIGHT_REFRESH_THRESHOLD` new items
arrive.

### Governance

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/campaigns/{public_id}/governance` | Tally, eligibility, viewer context, chain records |
| `POST` | `/api/campaigns/{public_id}/vote` | `{"choice": "REFUND" \| "CONTINUE"}` |
| `POST` | `/api/campaigns/{public_id}/governance/close` | Admin only; applies the outcome |
| `GET` | `/api/votes/my` | The caller's voting record |

A vote is rejected (409/403) when the campaign is not in `GOVERNANCE`, the round
is closed or expired, the caller has no verified contribution, the caller already
voted, or the choice is not one of the campaign's predefined options.

Closing a round only *decides*; it moves no money. A `REFUND` decision — whether
voted or from the `AUTOMATIC_REFUND` rule — puts the campaign and its
contributions into `REFUND_PENDING`. The worker then executes them:

```
contribution  REFUND_PENDING -> REFUNDED
payment       CAPTURED -> REFUND_INITIATED -> REFUNDED
campaign      REFUND_PENDING -> CLOSED   (once every contribution has settled)
```

`REFUND_INITIATED` is what makes the sweep re-entrant: a payment already in that
state is skipped rather than refunded a second time. Under Razorpay the
`refund.*` webhook completes the transition; the demo provider settles
synchronously. Set `AUTO_PROCESS_REFUNDS=false` to hold at `REFUND_PENDING` and
require an operator.

### Blockchain

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/blockchain/status` | Provider, network, contract, pending count |
| `GET` | `/api/blockchain/transactions/{tx_hash}` | One record |
| `POST` | `/api/blockchain/contributions/{id}/retry` | Retries a failed anchor |
| `GET` | `/api/blockchain/pending` | Admin only |

### Dashboards

| Method | Path |
|---|---|
| `GET` | `/api/creator/dashboard` |
| `GET` | `/api/creator/campaigns/{public_id}/analytics` |
| `GET` | `/api/contributor/dashboard` |

### Admin

| Method | Path | Notes |
|---|---|---|
| `GET` | `/api/admin/dashboard` | Platform metrics |
| `GET` | `/api/admin/campaigns/pending` | Review queue |
| `GET` | `/api/admin/campaigns` | All campaigns, filterable |
| `GET` | `/api/admin/campaigns/{public_id}` | Full review panel |
| `POST` | `/api/admin/campaigns/{public_id}/approve` | Publishes and issues the QR |
| `POST` | `/api/admin/campaigns/{public_id}/reject` | Requires a reason |
| `POST` | `/api/admin/campaigns/{public_id}/request-changes` | Returns to `DRAFT`; fee is not recharged |
| `GET` | `/api/admin/audit-logs` | Filter by `action` and `entity_type` |
| `GET` | `/api/admin/payments` · `/users` · `/blockchain/transactions` | Platform browsing |
| `GET` | `/api/admin/demo/controls` | Available demo actions |
| `POST` | `/api/admin/demo/control` | Runs one; **403 when `DEMO_MODE=false`** |

---

## Rate limits

Fixed window, per IP and path.

| Scope | Default |
|---|---|
| `/api/auth/login`, `/api/auth/register` | 10 / minute |
| Everything else | 120 / minute |

Exceeding a limit returns 429 with `Retry-After`.

---

## Webhook payloads

`POST /api/webhooks/razorpay` verifies `X-Razorpay-Signature` against the **raw
request body** before parsing anything. Handled events:

- `payment.captured` / `order.paid` → capture the payment, create the contribution
- `payment.failed` → record the failure reason
- `refund.*` → mark the payment refunded

Idempotency comes from a unique `webhook_events.event_id`. A redelivered event
returns `{"status": "duplicate", "processed": false}` and changes nothing.
