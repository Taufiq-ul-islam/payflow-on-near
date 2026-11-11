# PayFlow — Developer Documentation

This document describes PayFlow's architecture, development environment, payment and refund workflows, database design, and current implementation status.

> **Status:** NEAR testnet prototype. Direct NEAR and cross-chain payment flows have been exercised successfully. Direct NEAR and cross-chain refunds have also been completed successfully. This is not a production deployment.

## 1. Project Objective

PayFlow aims to simplify cryptocurrency payments for freelancers.

The application allows freelancers to:

- Create invoices denominated in USD.
- Share public payment links.
- Receive settlement in USDC on NEAR.
- Track invoice, payment, and refund statuses.
- Maintain payment records for bookkeeping.

Clients should be able to pay using supported assets and networks without needing to understand the underlying settlement process.

The project targets the NEAR hackathon **Real-World Money** track (`realworld`).

## 2. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Smart contract | Rust, near-sdk |
| Blockchain | NEAR Protocol |
| Payment integration | Tidepool sandbox |

## 3. Repository Structure

```text
.
├── backend/
│   └── app/
│       ├── api/
│       ├── core/
│       ├── integrations/
│       ├── models/
│       └── schemas/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   ├── lib/
│   └── types/
├── contracts/
│   └── payflow/
└── docs/
```

This is a conceptual overview rather than an exhaustive file listing.

## 4. Network and Provider Configuration

The current implementation uses NEAR testnet and Tidepool sandbox.

| Configuration | Value |
|---|---|
| Tidepool base URL | `https://www.usetidepool.tech` |
| NEAR network | `testnet` |
| NEAR RPC | `https://rpc.testnet.near.org` |
| USDC asset ID | `nep141:usdc.tidepool-sandbox.testnet` |
| USDC decimals | `6` |
| Frontend local URL | `http://localhost:3000` |
| Backend local URL | `http://localhost:8000` |
| Frontend API prefix | `/api` |

### Amount conversion

USDC uses six decimal places.

```python
usdc_base_units = usd_amount * 1_000_000
```

For example:

```text
USD 1.00 = 1000000 USDC base units
```

Use decimal arithmetic for monetary calculations. Avoid binary floating-point arithmetic for financial amounts.

## 5. Local Development Setup

### Prerequisites

- Node.js compatible with the frontend dependencies.
- Python compatible with the backend dependencies.
- PostgreSQL.
- NEAR testnet account and wallet.
- Access to the Tidepool sandbox.

### Backend setup

1. Navigate to `backend/`.
2. Create and activate a Python virtual environment.
3. Install dependencies from the project's dependency manifest.
4. Create the PostgreSQL database.
5. Configure the backend environment.
6. Apply the project's SQL schema and migrations.
7. Start the FastAPI application using the configured ASGI entry point.

### Frontend setup

1. Navigate to `frontend/`.
2. Install dependencies.
3. Configure the backend API URL.
4. Start the Next.js development server.
5. Open `http://localhost:3000`.
6. Connect a NEAR testnet wallet.

The frontend API URL has used:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000/api
```

### Backend environment

The backend settings include configuration for:

- NEAR network and RPC URL.
- PayFlow contract ID and optional admin ID.
- Relayer URL and credentials.
- Internal API authentication.
- Relayer gas limit.
- Tidepool/provider configuration.
- USDC asset ID and decimals.
- Frontend URL.
- Authentication cookie and session behavior.

Known testnet values:

```env
NEAR_NETWORK=testnet
NEAR_RPC_URL=https://rpc.testnet.near.org
USDC_ASSET_ID=nep141:usdc.tidepool-sandbox.testnet
USDC_DECIMALS=6
FRONTEND_URL=http://localhost:3000
```

These are configuration examples. Confirm the exact accepted variable names in `backend/app/core/config.py` before creating the local `.env` file.

Never commit private keys, API keys, database passwords, or session secrets.

## 6. Architecture

### Frontend

The Next.js application provides:

- Freelancer dashboard.
- Invoice creation and listing.
- Invoice management views.
- Public invoice payment page.
- Payment history.
- Client management.
- Settings and wallet authentication.
- Shared API utilities and UI components.

The public payment page is available under:

```text
/pay/[invoiceId]
```

### Backend

The FastAPI application handles:

- Wallet authentication.
- Invoice creation and retrieval.
- Payment asset discovery.
- Payment attempt creation and processing.
- Payment settlement and reconciliation.
- Refund quote generation.
- Refund approval and submission.
- Refund reconciliation.

SQLAlchemy models persist the application data in PostgreSQL.

### Smart contract and relayer

The project includes a Rust smart contract built with `near-sdk`.

The integration includes NEP-366/meta-transaction support and a relayer for sponsored contract interactions.

Sponsored contract calls should not be confused with every wallet transaction. Wallet actions outside the sponsored contract path may still require the relevant account to pay network fees.

## 7. Authentication

The backend wallet authentication flow uses a challenge-and-verification process.

1. The frontend requests an authentication challenge.
2. The wallet signs the challenge using NEP-413.
3. The backend verifies the signature and account access key.
4. A server-side session is created.
5. The session is returned through the `payflow_session` cookie.
6. Authenticated requests include the session cookie.

The NEP-413 message is intended for application authentication, not authorization for arbitrary transactions.

The implemented challenge lifetime is five minutes. Session duration and cookie security behavior are configurable.

Production deployment must use HTTPS and secure cookie settings.

## 8. Payment Workflow

The payment flow follows this general sequence:

1. Freelancer creates an invoice in USD.
2. Client opens the public payment page.
3. Frontend retrieves available payment assets from the backend.
4. Client selects an available payment option.
5. Backend creates a payment attempt.
6. Provider and blockchain operations process the payment.
7. Backend verifies and reconciles settlement information.
8. Invoice is marked paid after settlement is accepted.

### Direct NEAR payment

The direct NEAR path supports the configured NEAR USDC settlement asset.

A tested NEAR-hosted ETH token-to-USDC flow is a NEAR-to-NEAR token swap. It is not an Ethereum mainnet payment.

### Cross-chain payment

The cross-chain testnet path uses Tidepool sandbox.

The payment attempt records the source payment details and resulting settlement information. The backend reconciles the provider response and transaction evidence before accepting settlement.

Supported assets and networks depend on the provider's current configuration. Do not assume every asset or network is available.

### Multiple payment attempts

Multiple payment attempts for an invoice are intentional.

The system must preserve individual attempts and prevent an additional settlement from silently overwriting an already-paid invoice.

Unexpected or duplicate settlements should remain separately identifiable for investigation and refund handling.

## 9. Refund Workflow

Refunds are stored separately from the original payment.

This preserves the original payment history and allows refund transactions to be tracked independently.

The refund lifecycle includes:

1. Request a refund quote.
2. Validate the quote metadata and expiry.
3. Await freelancer approval.
4. Submit the refund using the selected route.
5. Reconcile provider and destination transaction information.
6. Persist the final refund status and transaction evidence.

### Tested refund paths

- Direct NEAR refund — successfully tested.
- Cross-chain refund — successfully tested.

The cross-chain reconciliation flow validates correlation information and provider status, identifies the destination transaction hash, and persists the refund transaction record.

The refund transaction model uses a UUID primary key. Reconciliation explicitly creates this ID when inserting the transaction record.

### Important refund handling

- Do not submit a second refund transfer simply because a UI label appears stale.
- If a transaction has already been submitted, continue using the existing transaction and reconciliation flow.
- Keep the original payment record intact.
- Record refund status and transaction evidence in refund-specific records.
- `PROCESSING` means the refund is still in progress, not that it has succeeded.
- Failed or review states require investigation using provider status, correlation ID, and transaction evidence.

## 10. Database Design

The main persisted concepts include:

| Model | Purpose |
|---|---|
| User | Freelancer wallet identity |
| AuthChallenge | Wallet authentication challenge |
| UserSession | Authenticated application session |
| Invoice | USD invoice and its lifecycle |
| PaymentAttempt | Individual attempt to pay an invoice |
| Transaction | Payment transaction evidence |
| Refund | Refund lifecycle linked to the original payment |
| RefundTransaction | Source/destination transaction evidence for a refund |

The invoice stores a reference to the payment attempt accepted as settling it, along with payment timing information.

Multiple payment attempts may exist for one invoice.

Refund records do not replace or delete the original payment record.

### Schema management

Database changes are managed through SQL schema and migration scripts.

`Base.metadata.create_all()` may be used as a development convenience, but it should not replace reviewed SQL migrations for production schema management.

## 11. API Overview

The backend API is mounted under `/api`.

| Route group | Purpose |
|---|---|
| `/api/auth` | Wallet challenge, verification, session lookup, logout |
| `/api/invoices` | Invoice creation, listing, public invoice data, management |
| `/api/payments` | Token discovery, payment attempts, submission, status |
| `/api/refunds` | Refund quotes, approval, submission, reconciliation |

For example, the payment token discovery endpoint is:

```text
/api/payments/tokens
```

The exact HTTP methods, schemas, and response fields should be checked in the current FastAPI router and Pydantic schema definitions.

## 12. Security and Production Readiness

PayFlow is a testnet prototype. Before handling real funds, the project needs further review and hardening.

Key areas include:

1. **Identity and access:** verify authentication, session security, and ownership checks for freelancer-only operations.
2. **Input validation:** validate amounts, asset identifiers, network identifiers, and wallet/account formats.
3. **Provider verification:** validate signatures, quote expiry, correlation IDs, and provider status responses.
4. **Idempotency:** prevent duplicate payment/refund submissions and repeated reconciliation side effects.
5. **Settlement integrity:** only mark invoices paid after verified settlement.
6. **Refund integrity:** bind refunds to original successful payments and preserve destination transaction evidence.
7. **Secrets and transport:** use HTTPS, secure cookies, secret management, and key rotation.
8. **Database safety:** use reviewed migrations, backups, constraints, and appropriate transaction boundaries.
9. **Monitoring:** add structured logs, tracing, alerts, and recovery procedures.
10. **Independent review:** complete contract, backend, and integration security reviews before production.

### Security roadmap

These are release gates, not claims that every item is already production-complete:

- Identity and access hardening.
- API/input protection and abuse controls.
- Payment verification and idempotency.
- Refund integrity and recovery.
- Infrastructure, secrets, and backups.
- Monitoring, incident response, and independent security review.

## 13. Testing and Verification

The following flows have been exercised on NEAR testnet:

- Wallet authentication.
- USD invoice creation and public payment link.
- Direct NEAR token payment with USDC settlement.
- Cross-chain payment through Tidepool sandbox.
- Direct NEAR refund.
- Cross-chain refund.
- Sponsored NEP-366 contract interaction and contract storage verification.

These are functional testnet validations, not a formal audit or production certification.

Use small test invoices and dedicated testnet accounts. Verify the invoice, payment attempt, provider response, transaction record, refund record, and destination transaction independently.

## 14. Known Limitations

- The application currently targets testnet.
- Tidepool sandbox is the current payment integration.
- Official 1Click API integration is not currently implemented.
- Available payment assets and networks depend on provider configuration.
- Mainnet deployment is not part of the verified implementation.
- Production monitoring, compliance review, and independent security audits remain outstanding.
- Do not assume Redis or other optional infrastructure is deployed unless the active environment explicitly configures it.
- Do not assume invoice management operations beyond those exposed by the current API/UI.

## 15. Future Prospects

1. **Official 1Click API integration:** integrate the official 1Click API when the project moves beyond its current sandbox/testnet setup.
2. **Mainnet deployment:** deploy and validate the contract, relayer, backend, and payment routes after security and operational review.
3. **Broader asset/network coverage:** expand payment choices according to provider support, liquidity, and tested routes.
4. **Relayer hardening:** improve sponsored transaction monitoring, key management, quotas, and recovery.
5. **Accounting improvements:** refine CSV export fields and workflows with bookkeeper feedback.
6. **Observability:** add transaction-level tracing, alerts, and dashboards for stuck payments and refunds.
7. **Security review:** arrange independent smart contract, backend, and integration reviews before real-fund usage.

## 16. References

- NEAR documentation: https://docs.near.org/
- Tidepool sandbox: https://www.usetidepool.tech
- Next.js documentation: https://nextjs.org/docs
- FastAPI documentation: https://fastapi.tiangolo.com/
- SQLAlchemy documentation: https://docs.sqlalchemy.org/

---

**PayFlow — make crypto payments fit the invoice, not the other way around.**
