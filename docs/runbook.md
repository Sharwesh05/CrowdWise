# CrowdWise — Local Runbook

Operating the stack on a developer machine: the commands, the provider
switches, and the failure modes that have actually bitten us with the fix for
each. `deployment.md` covers production; this is for running the demo.

---

## 1. Start from nothing

```bash
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend python seed.py
```

Then open <http://localhost:3000>. Accounts are `admin@example.com`,
`creator@example.com`, `contributor@example.com`, password `Demo@12345`.

Migrations are **not** run automatically — `backend.Dockerfile` says so
deliberately, so a schema change stays an explicit, reviewable step.

---

## 2. Rebuilding

There is no source bind-mount for the backend or the frontend. Editing a file
on the host does nothing until you rebuild.

| You changed | Command |
|---|---|
| `.env` (backend values) | `docker compose restart backend worker` |
| `.env` `NEXT_PUBLIC_*` | `docker compose up --build -d frontend` |
| Backend `.py` | `docker compose up --build -d backend worker` |
| Frontend `.tsx` / `.ts` | `docker compose up --build -d frontend` |
| `docker-compose.yml` | `docker compose up -d` |
| `infrastructure/caddy/Caddyfile` | `docker compose --profile https restart caddy` |
| A new Alembic migration | rebuild backend, then `alembic upgrade head` |

Always rebuild `worker` alongside `backend` — they share one image, and
rebuilding only `backend` leaves the worker on stale code.

`NEXT_PUBLIC_*` values are inlined at frontend **build** time, so changing one
needs `--build`, not a restart.

---

## 3. Full reset

```bash
docker compose down -v          # -v drops postgres_data: all data gone
docker compose up --build -d
docker compose exec backend alembic upgrade head        # never skip this
docker compose exec backend python seed.py
```

**After any `down -v` you must run migrations before using the app.** The
volume held the schema; without it every query fails with `UndefinedTable`
while the containers still report healthy.

`down -v` also gives the chain container a fresh node. It redeploys to the same
deterministic address, so `CONTRACT_ADDRESS` stays valid.

---

## 4. Seeding

```bash
docker compose exec backend python seed.py            # first run
docker compose exec backend python seed.py --reset    # drop and reseed
```

Three things to know:

- **`DEMO_MODE=true` is required.** The seed refuses to run otherwise.
- **`PAYMENT_PROVIDER` must be `demo`.** The seed fabricates historical payments
  with `simulate_success`, which real gateways refuse by design. To seed while
  running Razorpay, override for that one command:
  ```bash
  docker compose exec -e PAYMENT_PROVIDER=demo backend python seed.py --reset
  ```
- **`--reset` leaves Alembic unstamped.** It rebuilds the schema with
  `Base.metadata.create_all`, which never records a revision, so the next
  `alembic upgrade head` tries to replay the initial migration and fails with
  `relation "users" already exists`. Fix:
  ```bash
  docker compose exec backend alembic stamp head
  ```

Seeding with `AI_PROVIDER=nvidia` makes two real model calls per campaign and
takes minutes. For a fast seed, override it — then run a real analysis live
during the demo, which shows better anyway:

```bash
docker compose exec -e AI_PROVIDER=mock -e PAYMENT_PROVIDER=demo backend python seed.py --reset
```

---

## 5. Provider switches

Every provider is independent. The defaults are a zero-credential demo.

| Variable | Demo default | Real |
|---|---|---|
| `DEMO_MODE` | `true` | `false` in production only |
| `AI_PROVIDER` | `mock` | `nvidia` |
| `SENTIMENT_PROVIDER` | `mock` | `nvidia` or `xlm-roberta` |
| `PAYMENT_PROVIDER` | `demo` | `razorpay` |
| `BLOCKCHAIN_PROVIDER` | `mock` | `web3` |

`DEMO_MODE` and `PAYMENT_PROVIDER` are unrelated: demo mode plus a real
Razorpay gateway is a supported and useful combination.

### NVIDIA NIM

```
AI_PROVIDER=nvidia
SENTIMENT_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-...
NVIDIA_MODEL=nvidia/nemotron-3-super-120b-a12b
NVIDIA_TIMEOUT_SECONDS=240
```

- **Being listed by `/v1/models` does not mean your key can run it.** An
  unentitled model returns 404 on every request. Check first:
  ```bash
  curl -s -H "Authorization: Bearer $NVIDIA_API_KEY" \
    https://integrate.api.nvidia.com/v1/models | jq -r '.data[].id'
  ```
- **Keep the timeout generous.** Observed latency on one model ranged 28s to
  146s for a single campaign analysis. At 90s, half of a seed run degraded to
  the heuristic fallback.
- **Leave `NVIDIA_MAX_TOKENS` unset.** A cap sized for a plain instruct model
  truncates a reasoning model mid-thought, before it emits any JSON.
- Sentiment is batched: one call per 20 comments, not one per comment.

### Razorpay on localhost

```
PAYMENT_PROVIDER=razorpay
RAZORPAY_KEY_ID=rzp_test_...
RAZORPAY_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=          # leave empty
```

No webhook is needed locally. `POST /api/payments/verify` — the post-checkout
callback — verifies the HMAC signature and records the contribution itself. The
webhook only adds out-of-band events (a payment captured after the browser
closed, a dashboard refund) and flips a `webhook_verified` display flag. It
needs a public HTTPS URL, so it cannot reach `localhost` at all.

The admin **"simulate payment"** control stops working under `razorpay` — pay
with test card `4111 1111 1111 1111`, any future expiry, any CVV.

### Refunds

Money only ever leaves through the payment provider — never through the chain.
The lifecycle:

```
outcome decides REFUND            campaign  -> REFUND_PENDING
  (a contributor vote, or the                 contributions -> REFUND_PENDING
   AUTOMATIC_REFUND rule)
worker sweep calls the gateway    payment   -> REFUND_INITIATED
gateway confirms                  payment   -> REFUNDED
  (synchronously under the demo               contribution -> REFUNDED
   provider; by `refund.*` webhook
   under Razorpay)
last contribution settles         campaign  -> CLOSED
```

The sweep runs in the worker every 30s and is governed by
`AUTO_PROCESS_REFUNDS`. Set it to `false` to keep an operator in the loop:
campaigns then hold at `REFUND_PENDING` until someone runs the refund action.

Refunding is safe to run repeatedly. Each payment is guarded on its own status,
so a second sweep over a refund that is still in flight skips it rather than
sending the contributor their money twice — and under Razorpay, which settles
asynchronously, that overlap is the normal case rather than an edge one.

Under `razorpay` the `refund.*` webhook is what completes a refund, so without a
reachable webhook URL refunds will sit at `REFUND_INITIATED`: the money has been
sent, but CrowdWise cannot see the confirmation.

### Blockchain

```
BLOCKCHAIN_PROVIDER=web3
BLOCKCHAIN_RPC_URL=http://blockchain:8545
BLOCKCHAIN_CHAIN_ID=31337
CONTRACT_ADDRESS=0x5FbDB2315678afecb367f032d93F642f64180aa3
BLOCKCHAIN_PRIVATE_KEY=0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80
```

- `BLOCKCHAIN_RPC_URL` must be `http://blockchain:8545` inside Compose.
  `localhost` only works when the backend runs on the host.
- **Do not generate a key for the local chain.** The Hardhat node derives its
  accounts from a published mnemonic and prints all 20 at startup
  (`docker compose logs blockchain`). Use **account #0** — `scripts/deploy.ts`
  makes it the contract's `recorder`, and every write function is
  `onlyRecorder`, so any other key reverts with `NotRecorder`.
- Confirm your choice against the `recorder` field in
  `blockchain/deployments/localhost.json`.
- That key is publicly known. Never send real funds to its address, and never
  reuse it on a public network.
- `BLOCKCHAIN_EXPLORER_URL` stays empty locally — no explorer indexes a Hardhat
  node. The UI hides the link when it is unset.
- Re-seeding against a chain that still holds the previous run reverts with
  `CampaignExists`: campaign refs derive from the title, so identical titles
  produce identical refs. Recreate the chain when you reset the database:
  ```bash
  docker compose up -d --force-recreate blockchain
  ```

---

## 6. HTTPS and phone access

The stack serves plain HTTP on `:3000` and `:8000`, which is fine on this
machine and broken on a phone: **browsers expose the camera only in a secure
context** (HTTPS or localhost), so the in-page QR scanner cannot run over
`http://<lan-ip>:3000` at all. The HTTPS proxy fixes that, and puts the app and
API on one origin so CORS stops applying.

The frontend does **not** hard-code an API address. `frontend/lib/api.ts`
resolves it from the address the page was opened on:

| Page opened on | API calls go to |
|---|---|
| `https://localhost`, `https://<lan-ip>` (Caddy) | the same origin — relative `/api/*` |
| `http://localhost:3000`, `http://<lan-ip>:3000` | same host, port `8000` |

So one build works on localhost *and* over the LAN, and a new DHCP address needs
no frontend rebuild. Setting `NEXT_PUBLIC_API_URL` overrides all of it with a
fixed origin — leave it empty unless the API really lives on another host.

### One-time setup

Generate a certificate naming *your* address. The IP in `subjectAltName` is what
browsers match against — a certificate without it is rejected outright:

```bash
cd infrastructure/caddy
openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
  -keyout tls.key -out tls.crt \
  -subj "/CN=CrowdWise local demo" \
  -addext "subjectAltName=IP:192.168.1.18,IP:127.0.0.1,DNS:localhost"
```

Find your address with `ip -4 addr show scope global | grep -oP 'inet \K[\d.]+'`.
Both files are gitignored: a private key never belongs in the repository.

Then point the *backend* at the HTTPS origin in `.env`. `FRONTEND_URL` is what
the QR codes encode, so it must name the address a phone can reach — not
localhost:

```
FRONTEND_URL=https://192.168.1.18
BACKEND_URL=https://192.168.1.18
NEXT_PUBLIC_API_URL=
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,https://localhost,https://127.0.0.1,http://192.168.1.18:3000,https://192.168.1.18
```

These are read at startup, so a restart is enough:

```bash
docker compose restart backend worker
```

The `CORS_ORIGINS` entries only matter for the direct HTTP ports; through Caddy
every call is same-origin.

### Starting it

Caddy sits behind the `https` profile, so a plain `docker compose up` never
starts it and never binds port 443:

```bash
docker compose --profile https up -d caddy          # start
docker compose --profile https restart caddy        # reload after editing the Caddyfile
docker compose --profile https logs -f caddy        # logs
docker compose --profile https stop caddy           # stop; HTTP on :3000/:8000 still works
```

The Caddyfile is mounted read-only and read at startup, so an edit needs a
restart. Only 443 is published; Caddy's admin API on 2019 is deliberately not
exposed, since it can reconfigure the running server.

Then open **`https://192.168.1.18`** on the phone and tap through the
certificate warning once. On this machine the same stack answers on
**`https://localhost`** — the certificate names `localhost` and `127.0.0.1` as
well as the LAN IP — and the plain `http://localhost:3000` still works too. The certificate is self-signed, so that warning is
expected; a public deployment would use a CA-issued one, which Caddy can obtain
automatically given a real domain.

Check it from this machine with `-k`, which accepts the self-signed certificate
the same way the phone does after you tap through:

```bash
curl -sk -o /dev/null -w "%{http_code}\n" https://192.168.1.18/health
curl -sk https://192.168.1.18/api/public/campaigns
```

### If your IP changes

The address is handed out by DHCP, so it moves on a lease renewal, a reboot, or
a different venue's Wi-Fi. Four things are pinned to it, and two fail in ways
that do not obviously point at the address.

1. **Find the new one.** Take the Wi-Fi address, not the `172.x` Docker bridges.

   ```bash
   ip -4 addr show scope global | grep -oP 'inet \K[\d.]+'
   ```

2. **Regenerate the certificate.** Browsers match the address you typed against
   `subjectAltName`, so a stale certificate is a hard rejection, not a
   tap-through warning.

   ```bash
   cd infrastructure/caddy
   openssl req -x509 -newkey rsa:2048 -nodes -days 825 \
     -keyout tls.key -out tls.crt \
     -subj "/CN=CrowdWise local demo" \
     -addext "subjectAltName=IP:<new-ip>,IP:127.0.0.1,DNS:localhost"
   ```

3. **Update `.env`** — `FRONTEND_URL`, `BACKEND_URL`, and the LAN entries in
   `CORS_ORIGINS`. Leave `NEXT_PUBLIC_API_URL` empty; the frontend follows
   whatever address you open it on.

4. **Restart.** No frontend rebuild is needed, because no address is compiled
   into the bundle.

   ```bash
   docker compose restart backend worker
   docker compose --profile https restart caddy
   ```

5. **Existing QR codes are dead.** `qr_service.campaign_url`
   (`backend/app/services/qr_service.py`) builds them from `FRONTEND_URL`, so
   anything already printed or screenshotted points at the old address —
   redisplay them. Note the campaign URL is also **persisted** into audit and
   blockchain metadata when a campaign is published, so historical records keep
   the old address; changing the env does not rewrite them.

6. **Verify.**

   ```bash
   curl -sk -o /dev/null -w "%{http_code}\n" https://<new-ip>/health
   curl -sk https://<new-ip>/api/public/campaigns
   ```

### Gotchas

| Symptom | Cause |
|---|---|
| `TLS alert internal error` / `HTTP 000` | Certificate does not name the address. SNI cannot carry an IP, so the cert must be supplied explicitly (it is) and must list the IP in `subjectAltName`. |
| Page loads, all data fails | `NEXT_PUBLIC_API_URL` was set to a stale origin and is overriding the runtime one. Clear it and rebuild the frontend. |
| Phone cannot reach the host at all | Different network — guest SSID or mobile data. Many routers isolate guest clients from the LAN. |
| Camera still refuses | Confirm the address bar shows `https://`. The scanner is unavailable on any plain-HTTP LAN address. |
| QR opens a dead link | `FRONTEND_URL` is what the QR encodes. If it still says `localhost`, the phone resolves that to itself. |
| `ERR_CERT_COMMON_NAME_INVALID`, or a certificate naming the wrong address | The IP changed since the certificate was generated — see *If your IP changes*. |
| `npm run dev` calls the wrong API host | `frontend/.env.local` sets `NEXT_PUBLIC_API_URL`. Next reads that file, not the repo-root `.env`, and it is gitignored so the divergence is invisible in the repo. Comment the line out to go back to the derived address. |

After switching to HTTPS, `http://192.168.1.18:3000` keeps working — its calls
go to `http://192.168.1.18:8000`, which `CORS_ORIGINS` allows. It just cannot
use the camera, so use the HTTPS address for anything involving the scanner.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| "Could not load campaigns / could not reach the API" | API returns 500, not unreachable. Usually `UndefinedTable` — no schema after a `down -v` | `docker compose exec backend alembic upgrade head` |
| `relation "users" already exists` on upgrade | `seed.py --reset` left Alembic unstamped | `alembic stamp head`, then upgrade |
| AI analysis saved as `DEGRADED` | model call timed out or the id is unentitled. The stored `error` column says which | raise `NVIDIA_TIMEOUT_SECONDS`, or pick an entitled model |
| `Model 'x' is not available on this account` | listed but unentitled on NIM | list `/v1/models` and choose one that runs |
| `Payment simulation is not available for this provider` | seeding under `PAYMENT_PROVIDER=razorpay` | re-run with `-e PAYMENT_PROVIDER=demo` |
| `Database already contains campaigns` | seed is not idempotent | add `--reset` |
| Every chain write reverts `NotRecorder` | key is not the contract's recorder | use account #0, or `setRecorder` from the owner |
| Razorpay checkout / UPI QR renders *behind* the dialog | our `Dialog` is a native `<dialog>` in the browser top layer, which no z-index can cross | fixed: the dialog steps aside while the checkout sheet is open |
| `EACCES` writing `deployments/localhost.json` | SELinux denying a bind mount on a filesystem that cannot hold labels (NTFS/exFAT) | fixed: `security_opt: [label:disable]` on the `blockchain` service |
| `worker` shows **unhealthy** | it inherits the backend image's healthcheck, which curls `:8000/health`, but the worker runs the scheduler, not uvicorn | cosmetic; the scheduler is fine |
| Huge phantom diff across untouched files | CRLF committed from a Windows checkout | `.gitattributes` added; run `git add --renormalize .` once |
| Phone loads the page but no data | `NEXT_PUBLIC_API_URL` pins a stale origin, or the phone's origin is missing from `CORS_ORIGINS` | see section 6 — clear the variable, or serve the phone through the HTTPS proxy where CORS does not apply |
| "Start camera" does nothing over LAN | browsers block the camera outside a secure context | see section 6 — serve over HTTPS |
| Certificate error, or the phone worked yesterday and not today | the machine's LAN IP changed | see section 6 — *If your IP changes* |

`/health` reporting `"database":"ok"` only proves it can **connect** to
Postgres. It does not check that the schema exists — a green healthcheck is not
proof the app works.

---

## 8. Everyday commands

```bash
docker compose ps                                       # health of each service
docker compose logs -f backend                          # follow API logs
docker compose logs -f backend | grep -E "llm_|ai_"     # watch model calls
docker compose logs blockchain | head -30               # Hardhat accounts and keys
docker compose restart backend worker                   # pick up .env edits

# what the app thinks it is running
curl -s http://localhost:8000/health | jq

# poke the API directly
curl -s http://localhost:8000/api/public/campaigns | jq

# database
docker compose exec postgres psql -U crowdwise -d crowdwise -c "\dt"
docker compose exec postgres psql -U crowdwise -d crowdwise \
  -c "select public_id, status, title from campaigns order by id;"
```

Campaign ids are derived from the title (`CMP-N2R6YW`), not sequential, so read
them from the seed output or the query above rather than guessing.
