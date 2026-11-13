# PayFlow — Developer & Judge Reproduction Guide

> **Project:** PayFlow — crypto invoicing for freelancers who don't care about crypto  
> **NEAR Hackathon track:** Real-World Money (`realworld`)  
> **Current target:** NEAR mainnet + official NEAR Intents 1Click API  
> **Status:** Mainnet integration configuration. This repository is not represented as a production payment service; use operational controls and small-value transactions appropriate to your deployment.

This guide is written for a developer or automated judge starting from a clean clone. It gives explicit commands and observable outcomes. The detailed route contract is in [`API_REFERENCE.md`](API_REFERENCE.md); the demo script is in [`DEMO_GUIDE.md`](DEMO_GUIDE.md).

## 1. What to run

PayFlow is made of four separately configured pieces:

1. **Next.js frontend** — freelancer dashboard and public invoice payment page.
2. **FastAPI backend** — authentication, invoices, payment attempts, reconciliation, refunds and CSV export.
3. **PostgreSQL** — persistent application and transaction records.
4. **NEAR mainnet services** — PayFlow Rust contract, NEAR RPC and Pagoda Relayer. The official NEAR Intents 1Click API supplies token discovery, quotes, deposit submission and cross-chain status.

The Pagoda Relayer is an external Rust service. It is not bundled as an executable in this repository. The backend calls its `POST /send_meta_tx` endpoint.

## 2. Prerequisites

- Git
- Python 3.11+ (use the version compatible with the backend lock/dependency environment)
- Node.js 20+ and npm
- PostgreSQL
- Rust toolchain (`rustup`, `cargo`) for contract and relayer builds
- Docker Compose (recommended for the Pagoda Relayer)
- NEAR mainnet deployment details for the PayFlow contract and its restricted admin function-call key
- A funded mainnet relayer account/key for gas-sponsored contract calls
- Official NEAR Intents 1Click API access and the required JWT/API credential

Do not commit `.env`, wallet key files, relayer `account_keys`, database passwords, or API keys.

## 3. Clone and inspect

```bash
git clone <PUBLIC_PAYFLOW_REPOSITORY_URL>
cd <REPOSITORY_DIRECTORY>
git status --short
```

Expected: a clean working tree after clone.

Repository areas:

```text
backend/                 FastAPI application, SQLAlchemy models, migrations
frontend/                Next.js application
contracts/payflow/       Rust NEAR contract
backend/migrations/      SQL schema changes
docs/                    Developer, API and demo documentation
```

## 4. PostgreSQL

Create a database named `payflow` (or choose another name and use it consistently in `DATABASE_URL`).

Example using `createdb`:

```bash
createdb payflow
```

Or with `psql`:

```sql
CREATE DATABASE payflow;
```

The backend imports all SQLAlchemy models and calls `Base.metadata.create_all()` at startup for the model-defined base tables. The SQL files in `backend/migrations/` are incremental changes and must be applied to a database whose baseline tables exist. Do not blindly re-run non-idempotent `ALTER TABLE` migrations against an already migrated database.

For a fresh database, first start the backend once to create the model-defined base tables, stop it, then apply the migration files in dependency order:

```bash
cd backend
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/wallet_auth.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/payment_integration.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/refund_schema.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/alter_refund.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/one_click_refund.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f migrations/refund_quote_data_constraint.sql
```

If the database already contains these columns/tables, inspect the schema before applying. `alter_refund.sql` and `one_click_refund.sql` use `ALTER TABLE` and are not safe to apply twice.

## 5. Backend setup

```bash
cd backend
python -m venv .venv
```

Activate the environment:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `backend/.env` from `backend/.env.example` and set the real local values. Minimum settings:

```env
DATABASE_URL=postgresql+psycopg://postgres:<PASSWORD>@localhost:5432/payflow

NEAR_NETWORK=mainnet
NEAR_RPC_URL=https://rpc.mainnet.near.org

PAYFLOW_CONTRACT_ID=<deployed-payflow-contract.near>
PAYFLOW_CONTRACT_ADMIN_ID=<contract-admin-account.near>
PAYFLOW_ADMIN_FUNCTION_CALL_PUBLIC_KEY=ed25519:<FUNCTION_CALL_PUBLIC_KEY>
PAYFLOW_ADMIN_FUNCTION_CALL_PRIVATE_KEY=ed25519:<FUNCTION_CALL_PRIVATE_KEY>

RELAYER_URL=http://127.0.0.1:3030
RELAYER_API_KEY=<relayer-api-key-if-configured>
RELAYER_MAX_GAS=100000000000000
INTERNAL_API_KEY=<random-long-secret>

NEAR_INTENTS_BASE_URL=https://1click.chaindefuser.com
NEAR_INTENTS_API_KEY=<official-1click-jwt>

USDC_ASSET_ID=<NEAR_MAINNET_USDC_ASSET_ID>
USDC_DECIMALS=6

FRONTEND_URL=http://localhost:3000
AUTH_COOKIE_SECURE=false
AUTH_SESSION_DAYS=7
```

The backend's NEAR Intents client uses the official 1Click API base URL and its `/v0/tokens`, `/v0/quote`, `/v0/deposit/submit` and `/v0/status` endpoints. Keep the provider URL, credentials, network setting and asset identifiers aligned: do not combine mainnet 1Click with Tidepool sandbox credentials or testnet asset IDs. The 1Click API is used for cross-chain routing; direct NEAR USDC transfers are verified through the configured NEAR RPC.

Start the backend:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Expected checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/
```

Expected JSON:

```json
{"status":"healthy"}
```

and:

```json
{"name":"PayFlow","status":"running"}
```

OpenAPI documentation:

- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

## 6. Frontend setup

In a second terminal:

```bash
cd frontend
npm ci
```

Create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

Run:

```bash
npm run dev
```

Open `http://localhost:3000`.

For a production build check:

```bash
npm run build
npm run start
```

The frontend uses cookie-based sessions (`credentials: "include"`). Keep `FRONTEND_URL` in the backend aligned with the browser origin. For local HTTP development, use `AUTH_COOKIE_SECURE=false`; for an HTTPS deployment, set `AUTH_COOKIE_SECURE=true`. This cookie setting is independent of the NEAR network selected by `NEAR_NETWORK=mainnet`.

## 7. Build and deploy the PayFlow contract

The contract source is `contracts/payflow/`. It uses `near-sdk = 5.17.0`.

```bash
cd contracts/payflow
cargo test
cargo build --target wasm32-unknown-unknown --release
```

If the wasm target is not installed:

```bash
rustup target add wasm32-unknown-unknown
```

The resulting wasm is normally:

```text
target/wasm32-unknown-unknown/release/payflow.wasm
```

Deploy and initialize using the NEAR CLI version available to the operator. Example shape (replace the placeholders with your deployed mainnet contract details and use the intended deployment key):

```bash
near contract deploy <PAYFLOW_CONTRACT_ID> use-file target/wasm32-unknown-unknown/release/payflow.wasm
near contract call-function as-transaction <PAYFLOW_CONTRACT_ID> new json-args '{"admin":"<PAYFLOW_CONTRACT_ADMIN_ID>"}' prepaid-gas '100 Tgas' attached-deposit '0 NEAR' sign-as <DEPLOYER_ACCOUNT> network-config mainnet sign-with-plaintext-private-key send
```

CLI syntax varies by installed `near` version; if this command shape is not supported, use the equivalent `near deploy` and `near call` commands for that CLI release. Do not deploy or reinitialize a contract that already contains project data.

The contract's `record_settlement` method is admin-only and stores one settlement record per invoice ID. It stores a record submitted by the trusted backend after reconciliation; it is not an independent cross-chain proof verifier.

## 8. Build and run the Pagoda Relayer

### Why it is a separate dependency

PayFlow uses NEP-366 meta-transactions. The backend constructs and signs a delegate action for the configured admin function-call key, then sends it to the Pagoda Relayer. The relayer pays NEAR gas and broadcasts the transaction.

Official upstream repository: <https://github.com/near/pagoda-relayer-rs>

The upstream project is not included in this source archive. For judge reproducibility, pin it as a public Git submodule (recommended) or record the exact upstream commit and provide the same clone/build steps. Do not rely on an unpinned `develop` branch for a final judging run.

### Add a pinned public submodule before publishing

Judges must clone with:

```bash
git clone --recurse-submodules <PUBLIC_PAYFLOW_REPOSITORY_URL>
cd <REPOSITORY_DIRECTORY>
git submodule update --init --recursive
```

If the submodule is not added, the equivalent manual reproduction is:

```bash
git clone https://github.com/near/pagoda-relayer-rs.git
cd pagoda-relayer-rs
git checkout <THE_SAME_UPSTREAM_COMMIT_SHA>
```

### Configure relayer account

Configure a dedicated NEAR mainnet relayer account to pay relayed gas. It must hold sufficient mainnet NEAR for the sponsored contract calls. The upstream relayer expects a key JSON file under `account_keys/` with `account_id`, `public_key`, and `secret_key`. The upstream README notes that a copied NEAR credentials file may use `private_key`; rename that property to `secret_key` if required by the checked-out upstream version.

Example shape only — never commit actual credentials:

```json
[
  {
    "account_id": "<RELAYER_ACCOUNT_ID>",
    "public_key": "ed25519:<PUBLIC_KEY>",
    "secret_key": "ed25519:<PRIVATE_KEY>"
  }
]
```

Put this file in `vendor/pagoda-relayer-rs/account_keys/` and ensure it is ignored by Git.

### Configure `config.toml`

Start from the upstream `config.toml` and the upstream examples for the checked-out commit. Set:

- `port = 3030`
- `relayer_account_id` to the dedicated funded mainnet relayer account
- `keys_filename` to the key JSON file
- `network = "mainnet"`
- `rpc_url = "https://rpc.mainnet.near.org"`
- `use_whitelisted_contracts = true` and configure the PayFlow contract allowlist using the exact syntax in the pinned upstream examples
- Keep the relayer receiver allowlist restrictive where supported
- Disable optional Redis/allowance/FastAuth features unless the selected upstream config requires them

Do not use a broad no-filter configuration on an internet-facing service. PayFlow's own backend validates the action, but the relayer should also be configured with the narrowest upstream allowlist available.

### Build and run (Docker Compose)

From `vendor/pagoda-relayer-rs/`:

```bash
docker compose build
docker compose up -d
docker compose logs -f relayer
```

The upstream compose file maps port `3030` and mounts `config.toml` and `account_keys`. The upstream Dockerfile builds the Rust binary in a container. If Docker is unavailable, use the upstream native instructions:

```bash
cargo build --release
cargo run
```

Verify the local service is reachable before starting PayFlow's backend:

```bash
curl -i http://127.0.0.1:3030/
```

The root path may not be a health endpoint; an HTTP 404 still proves the TCP/HTTP server is reachable. Use the upstream OpenAPI UI at `http://127.0.0.1:3030/swagger-ui/` to inspect the actual endpoints for the pinned revision. The PayFlow integration specifically calls:

```text
POST http://127.0.0.1:3030/send_meta_tx
```

Stop it with:

```bash
docker compose down
```

**Important:** the relayer account pays gas. A relayer process without a funded mainnet account can start but cannot successfully sponsor transactions.

## 9. End-to-end judge smoke test

Use a dedicated application database and the intended mainnet deployment configuration. For any live-value demonstration, use a deliberately small invoice amount and follow the provider and network operational guidance.

### A. Confirm services

```bash
curl -sS http://127.0.0.1:8000/health
```

Open `http://localhost:3000`, and confirm the Pagoda Relayer is running on port 3030.

### B. Authenticate freelancer

1. Open `http://localhost:3000/login`.
2. Connect a NEAR mainnet wallet.
3. Sign the one-time NEP-413 authentication challenge.
4. Open `/dashboard/settings`.

Expected: the dashboard displays the authenticated NEAR account ID. `GET /api/auth/me` returns `authenticated: true`.

### C. Create invoice

1. Open `/dashboard/invoices/new`.
2. Enter client name/email, due date and at least one line item.
3. Create the invoice.
4. Open the created invoice management page and copy its public `/pay/<invoice-id>` link.

Expected: invoice appears in the invoice list with `PENDING` status and the public link opens without freelancer login.

### D. Complete a direct NEAR USDC payment

1. Open the public invoice link in a separate browser session/tab.
2. Choose the direct NEAR USDC option.
3. Connect the payer's NEAR mainnet wallet and submit the USDC transfer.
4. Wait for backend NEAR RPC reconciliation.

Expected:
- The payment attempt moves through processing and then `SUCCESS`.
- The invoice becomes `PAID`.
- A NEAR transaction hash/explorer link is stored.
- The backend records the accepted settlement on the PayFlow contract through the Pagoda Relayer when the relayer and contract settings are configured.

### E. Complete a cross-chain payment (optional; official 1Click API availability required)

1. Use the public payment link.
2. Choose a token/network shown by `GET /api/payments/tokens`.
3. Enter the payer refund address required by the selected route.
4. Create/commit the quote and follow the provider deposit instructions.
5. Submit the origin transaction hash.
6. Poll the payment status until final.

Expected: the provider status and transaction data are reconciled; the invoice is settled once. A second successful attempt is retained as a duplicate settlement/review case rather than silently overwriting the first settlement.

### F. Test refund

1. Open `/dashboard/payments`.
2. Select a successful payment and request a refund.
3. PayFlow uses the original payer network, wallet and asset metadata stored with the payment; the freelancer should not have to re-enter an arbitrary destination.
4. Approve the quote.
5. Submit the NEAR USDC source transfer shown by the refund flow.
6. Reconcile until final.

Expected:
- A separate refund record is created.
- The original payment remains unchanged.
- Direct NEAR refund and cross-chain refund use different settlement/reconciliation paths.
- `PROCESSING` is not displayed as `SUCCESS`; final success includes destination transaction evidence.

### G. CSV export

1. Open `/dashboard/invoices`.
2. Click the CSV export action.

Expected: a UTF-8 CSV download named `payflow_invoices.csv`.

## 10. API and flow references

- [`API_REFERENCE.md`](API_REFERENCE.md) — backend endpoints, auth requirements, payloads, frontend route map.
- [`DEMO_GUIDE.md`](DEMO_GUIDE.md) — short demo script and the concrete NEAR value proposition.

FastAPI's generated API reference is available at `/docs` when the backend is running.

## 11. Known limitations and deployment considerations

- The current mainnet integration targets the official NEAR Intents 1Click API at `https://1click.chaindefuser.com`, with NEAR mainnet RPC and mainnet contract/relayer configuration. Tidepool was used for the earlier testnet prototype and is retained in the acknowledgements for that work; it is not the active mainnet provider.
- Direct NEAR payments are NEP-141 USDC transfers verified through NEAR RPC.
- Cross-chain payments depend on provider availability and provider-reported status.
- The contract stores settlement attestations written by the backend after reconciliation. It is not a trustless verifier of the external chain swap.
- Refunds are full refunds to the original payer's stored network/wallet route in the current implementation; partial refunds are not the documented flow.
- Multiple payment attempts per invoice are intentional.
- Invoice update/delete endpoints are not currently implemented.
- A production deployment still requires independent security review, monitoring, hardened secrets/cookies, operational alerting, and an independently reviewed settlement verification model.
