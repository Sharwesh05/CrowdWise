# CrowdWise — Deployment

How to run CrowdWise locally, and what has to change before it faces real users
and real money.

---

## Local development

### Docker (recommended)

```bash
cp .env.example .env
docker compose up --build
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

Services:

| Service | Port | Health check |
|---|---|---|
| `frontend` | 3000 | `GET /` |
| `backend` | 8000 | `GET /health` |
| `worker` | — | process liveness |
| `postgres` | 5432 | `pg_isready` |
| `blockchain` | 8545 | `eth_blockNumber` |

The backend waits for Postgres to report healthy before starting. Migrations are
never applied automatically — that is an explicit command, so a deploy can never
silently alter a production schema.

### Without Docker

See the README. `DATABASE_URL=sqlite+pysqlite:///./crowdwise.db` gives a working
stack with no database server; the models are Postgres-compatible either way.

---

## Configuration

Everything comes from the environment. `.env.example` is the complete list.

### Provider switches

| Variable | Demo value | Production value |
|---|---|---|
| `DEMO_MODE` | `true` | `false` |
| `PAYMENT_PROVIDER` | `demo` | `razorpay` |
| `AI_PROVIDER` | `mock` | `nvidia` (or `gemma`) |
| `SENTIMENT_PROVIDER` | `mock` | `xlm-roberta` |
| `BLOCKCHAIN_PROVIDER` | `mock` | `web3` |
| `STORAGE_PROVIDER` | `local` | `s3` |
| `KYC_PROVIDER` | `demo` | *(a licensed vendor — see below)* |

### Production safety check

`Settings.assert_production_safe()` runs at startup when
`ENVIRONMENT=production` and refuses to boot if:

- `JWT_SECRET` or `COOKIE_SECRET` is a default or shorter than 32 characters
- `CHAIN_HASH_SALT` is still the development value
- `DEMO_MODE` is true
- `COOKIE_SECURE` is false
- `PAYMENT_PROVIDER=razorpay` with no `RAZORPAY_WEBHOOK_SECRET`

Generate secrets with:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## Going to production

### 1. Database

Use managed PostgreSQL (RDS, Cloud SQL, Neon, Supabase). Enable automated
backups and point-in-time recovery — `payments`, `contributions` and `votes` are
financial and governance records.

```bash
DATABASE_URL=postgresql+psycopg://user:password@host:5432/crowdwise
alembic upgrade head
```

Run migrations as a separate deploy step, before the new application version
starts serving.

### 2. Payments

```
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_live_xxxxxxxx
RAZORPAY_KEY_SECRET=<from the dashboard>
RAZORPAY_WEBHOOK_SECRET=<from the webhook config>
```

Configure the webhook to `POST https://api.yourdomain.com/api/webhooks/razorpay`
for `payment.captured`, `payment.failed`, `order.paid` and `refund.processed`.

The webhook endpoint must be publicly reachable and must **not** sit behind
authentication — it authenticates itself with an HMAC signature over the raw body.

**Payouts are not implemented.** Contributions are recorded, but disbursing money
to creators needs Razorpay Route or a linked-account structure behind the existing
`PaymentProvider` interface, plus the compliance work that comes with holding
other people's funds.

### 3. AI

```
AI_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-<key>
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
```

`nvidia` targets NVIDIA NIM: the hosted gateway above, or a self-hosted NIM
container reached by pointing `NVIDIA_BASE_URL` at it (no key needed then).

Being listed by `GET /v1/models` does not mean your key is entitled to run a
model — an un-entitled id returns 404. Verify before a demo:

```bash
curl -s -H "Authorization: Bearer $NVIDIA_API_KEY" \
  https://integrate.api.nvidia.com/v1/models | jq -r '.data[].id'
```

Leave `NVIDIA_MAX_TOKENS` and `NVIDIA_TEMPERATURE` unset unless you need them;
the request is model + messages only by default.
`AI_PROVIDER=nvidia` without `NVIDIA_API_KEY` fails the production safety check
rather than silently running on the heuristic analyst.

For any other OpenAI-compatible endpoint — Ollama, vLLM, a hosted gateway — use
`AI_PROVIDER=gemma` with `GEMMA_BASE_URL` / `GEMMA_API_KEY` / `GEMMA_MODEL`.

Either way the provider retries once and then degrades to the heuristic analyst,
marking the record `DEGRADED` rather than failing the request.

For sentiment, `SENTIMENT_PROVIDER=xlm-roberta` needs `transformers` and `torch`
in the image. The model loads lazily and once. On CPU it is comfortably fast
enough for feedback classification, which is a background job.

**Cost control is structural, not incidental:** individual comments go to the
cheap classifier; only aggregates and a small anonymised sample reach the LLM,
and insights are cached until enough new feedback arrives.

### 4. Blockchain

Deploy the registry to a public testnet or L2:

```bash
cd blockchain
BLOCKCHAIN_RPC_URL=https://... BLOCKCHAIN_PRIVATE_KEY=0x... \
  npx hardhat run scripts/deploy.ts --network testnet
```

Then:

```
BLOCKCHAIN_PROVIDER=web3
BLOCKCHAIN_RPC_URL=https://...
BLOCKCHAIN_CHAIN_ID=<chain id>
CONTRACT_ADDRESS=0x...
BLOCKCHAIN_PRIVATE_KEY=<recorder key>
BLOCKCHAIN_EXPLORER_URL=https://explorer.example
```

Operational notes:

- The recorder key signs every anchor. Keep it in a secret manager or a KMS, fund
  it with a monitored balance, and rotate it with `setRecorder()`.
- `CHAIN_HASH_SALT` protects on-chain references from correlation. Rotating it
  changes future hashes only; existing records stay valid and verifiable.
- An L2 keeps per-anchor gas negligible. A failed anchor is retried by the worker
  and never affects payment state.

### 5. Storage

```
STORAGE_PROVIDER=s3
STORAGE_ENDPOINT=https://<account>.r2.cloudflarestorage.com
STORAGE_BUCKET=crowdwise
STORAGE_ACCESS_KEY=...
STORAGE_SECRET_KEY=...
STORAGE_PUBLIC_BASE_URL=https://cdn.yourdomain.com
```

Requires `boto3` in the image (lazy-imported). Keep the bucket private and serve
through a CDN. Uploads are already validated by MIME allowlist, extension
allowlist, magic-byte sniff and size cap, and are stored under randomised keys —
a user-supplied filename never becomes a path.

### 6. KYC

`DemoKYCProvider` must be replaced. Implement `KYCProvider` against a licensed
vendor (Signzy, HyperVerge, Karza, IDfy) and register it in
`kyc_service.get_provider()`. Nothing in the campaign or application logic
changes — the gate already exists.

KYC data stays in PostgreSQL, is redacted from every log line, and is never sent
to the blockchain or to the LLM. Treat the `kyc_verifications` table as the most
sensitive data in the system: encrypt at rest, restrict access, and set a
retention policy.

---

## Security checklist before launch

- [ ] Strong `JWT_SECRET`, `COOKIE_SECRET`, `CHAIN_HASH_SALT` from a secret manager
- [ ] `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax`, HTTPS everywhere
- [ ] `CORS_ORIGINS` restricted to your exact frontend origin
- [ ] `DEMO_MODE=false` (this alone disables every demo control)
- [ ] Rate limiting moved to Redis for multi-node deployment
- [ ] Razorpay webhook secret configured and the endpoint reachable
- [ ] Database backups and PITR verified by an actual restore
- [ ] Chain recorder key funded, monitored and rotatable
- [ ] Logs shipped to a retained store; confirm no secrets or KYC fields appear
- [ ] Dependency and container scanning in CI
- [ ] Legal review of fundraising, refund and tax obligations

---

## Scaling notes

| Component | Current | When it needs to change |
|---|---|---|
| Background jobs | In-process threads | Jobs must survive a restart → Celery or RQ |
| Rate limiting | In-process, per node | More than one node → Redis |
| Sentiment | Synchronous in a worker thread | High feedback volume → a dedicated queue and batching |
| Chain anchoring | Serialised on one nonce | High throughput → a nonce manager or several recorder keys |
| Campaign listing | Direct queries with indexes | Large catalogue → a read replica or a search index |
| Refunds | Sequential | Thousands of contributors → a queued, resumable job |

The service-layer boundaries are the reason each of these is a contained change
rather than a rewrite.

---

## Monitoring

Watch these, because they are where the interesting failures show up:

- `/health` — liveness plus which providers are actually active
- Payments captured but not webhook-verified (surfaced on the admin dashboard)
- Contributions stuck in `BLOCKCHAIN_PENDING` or `BLOCKCHAIN_FAILED`
- Feedback stuck in `PENDING` sentiment
- AI analyses with status `DEGRADED` (the model endpoint is failing)
- 429 rates on the auth endpoints (credential stuffing)
- Governance rounds past their close time that have not been closed

Every request logs a request id, user id, method, path, status and duration.
Passwords, tokens, payment secrets, private keys and KYC fields are redacted by
the logging layer before anything is written.
