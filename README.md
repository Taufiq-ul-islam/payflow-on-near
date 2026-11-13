# PayFlow

**Crypto invoicing for freelancers who don't care about crypto.**

PayFlow lets freelancers create invoices in USD and share payment links with clients. Clients pay using crypto assets and networks supported by the **official NEAR Intents 1Click API**, while the intended freelancer settlement asset is **USDC on NEAR**.

The goal is to make crypto payments feel like ordinary invoicing: create an invoice, share a link, receive payment, track its status, and maintain bookkeeping records.

> **Project status:** Mainnet implementation targeting NEAR mainnet and the official NEAR Intents 1Click API. The earlier NEAR testnet/Tidepool prototype established and tested the direct and cross-chain payment flows, as well as direct and cross-chain refunds. PayFlow remains a project prototype, not a production payment service.

## How it works

1. A freelancer signs in using a NEAR wallet.
2. The freelancer creates an invoice denominated in USD.
3. PayFlow generates a public payment link.
4. The client opens the link and selects an available payment asset and network.
5. Cross-chain payments are routed through the official NEAR Intents 1Click API; direct NEAR USDC payments use the NEAR transfer path.
6. PayFlow tracks settlement and records the resulting payment information.
7. The freelancer can review invoice, payment, and refund activity.

The intended settlement asset for freelancers is USDC on NEAR.

## Current implementation

- USD-denominated invoices and public payment links.
- NEAR wallet authentication.
- Payment asset discovery through the official 1Click token registry.
- Direct NEAR and cross-chain payment flows.
- USDC settlement tracking on NEAR.
- Invoice and payment status tracking.
- Refund records separate from original payment records.
- Direct NEAR and cross-chain refund flows.
- Rust smart contract and NEP-366/meta-transaction relayer integration.
- Payment and bookkeeping records, including CSV export functionality where available.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js, React, TypeScript, Tailwind CSS |
| Backend | Python, FastAPI, Pydantic |
| Database | PostgreSQL, SQLAlchemy |
| Smart contract | Rust, near-sdk |
| Blockchain | NEAR Protocol (mainnet) |
| Cross-chain payment integration | NEAR Intents 1Click API |
| Gas-sponsored contract calls | NEP-366, Pagoda Relayer |

## Current network and provider

The current implementation is configured for:

- NEAR mainnet.
- NEAR mainnet RPC: `https://rpc.mainnet.near.org`.
- Official NEAR Intents 1Click API: `https://1click.chaindefuser.com`.
- Mainnet NEAR USDC asset configured through `USDC_ASSET_ID` and `USDC_DECIMALS`.

The backend uses the official 1Click API for token discovery, quote creation, deposit submission, and cross-chain status reconciliation. Direct NEAR USDC transfers are verified through NEAR RPC. Asset availability and routes are provider-dependent.

## Repository structure

```text
.
├── backend/              # FastAPI backend
├── frontend/             # Next.js frontend
├── contracts/
│   └── payflow/           # NEAR smart contract
└── docs/
    ├── README.md         # User and bookkeeper guide
    ├── DEVELOPERS.md     # Technical documentation
    ├── API_REFERENCE.md  # Backend API and frontend reference
    └── DEMO_GUIDE.md     # Demo narrative and walkthrough
```

This is a high-level representation of the repository.

## Getting started

PayFlow consists of independently run frontend and backend services.

1. Set up PostgreSQL.
2. Configure the backend environment for NEAR mainnet and the official 1Click API.
3. Apply the required SQL schema and migrations.
4. Configure the deployed PayFlow contract and Pagoda Relayer for NEAR mainnet.
5. Start the FastAPI backend.
6. Configure the frontend API URL.
7. Start the Next.js frontend and connect a NEAR mainnet wallet.

See [Developer Documentation](docs/DEVELOPERS.md) for setup and configuration details.

## Documentation

- [User Guide — Freelancers, Clients and Bookkeepers](docs/README.md)
- [Developer Documentation](docs/DEVELOPERS.md)
- [API & Frontend Reference](docs/API_REFERENCE.md)
- [Demo Guide](docs/DEMO_GUIDE.md)

## Limitations

- PayFlow is a prototype, not a production financial service.
- Mainnet transactions involve real assets and network fees; configure and operate the system accordingly.
- Supported assets and networks depend on official 1Click provider availability.
- The contract stores settlement attestations submitted by the backend after reconciliation; it does not independently verify external-chain swaps.
- Refunds currently follow the original payer's stored network and wallet route and are implemented as full refunds; partial refunds are not the documented flow.
- Production use requires independent security review, operational monitoring, hardened secrets/cookies, and review of the settlement verification model.
- Testnet assets do not represent real-world funds.

## Acknowledgements & Third-Party Infrastructure

PayFlow builds on the work of these projects and services:

- **[NEAR Intents 1Click API](https://1click.chaindefuser.com)** — Official mainnet API used for token discovery, cross-chain quotes, deposit submission, and settlement-status reconciliation.
- **[Tidepool](https://www.usetidepool.tech)** — Community-built NEAR Intents 1Click API sandbox used during the earlier testnet prototype for cross-chain quotes, deposits, swaps, and settlement testing. This credit is retained for that testnet implementation; Tidepool is not the current mainnet provider.
- **[Pagoda Relayer](https://github.com/near/pagoda-relayer-rs)** — NEP-366 meta-transaction relayer used to sponsor gas for PayFlow's settlement-recording contract interactions.
- **[NEAR Protocol](https://near.org)** — The blockchain infrastructure and intent-based ecosystem underlying PayFlow's settlement flow.

## Hackathon Track

Built for the NEAR hackathon **Real-World Money** track (`realworld`).

**PayFlow — make crypto payments fit the invoice, not the other way around.**
