# PayFlow

**Crypto invoicing for freelancers who don't care about crypto.**

PayFlow lets freelancers create invoices in USD and share payment links with clients. Clients pay using supported crypto assets and networks, while the intended freelancer settlement asset is **USDC on NEAR**.

The goal is to make crypto payments feel like ordinary invoicing: create an invoice, share a link, receive payment, track its status, and maintain bookkeeping records.

> **Project status:** Working NEAR testnet prototype. Direct NEAR and cross-chain payment flows have been tested. Both direct NEAR and cross-chain refunds have also been successfully tested. This is not a production payment service.

## How it works

1. A freelancer signs in using a NEAR wallet.
2. The freelancer creates an invoice denominated in USD.
3. PayFlow generates a public payment link.
4. The client opens the link and selects an available payment asset and network.
5. The payment is processed through the configured testnet payment provider.
6. PayFlow tracks settlement and records the resulting payment information.
7. The freelancer can review invoice and payment activity.

The intended settlement asset for freelancers is USDC on NEAR.

## Current implementation

- USD-denominated invoices and public payment links.
- NEAR wallet authentication.
- Payment asset discovery through the configured provider.
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
| Blockchain | NEAR Protocol |
| Payment integration | Tidepool sandbox |

## Current network and provider

The current implementation uses:

- NEAR testnet
- NEAR testnet RPC
- Tidepool sandbox: https://www.usetidepool.tech
- Testnet USDC on NEAR

**Important:** The current testnet implementation uses the Tidepool sandbox. The official 1Click API is not currently integrated and is listed as a future prospect.

## Repository structure

```text
.
├── backend/              # FastAPI backend
├── frontend/             # Next.js frontend
├── contracts/
│   └── payflow/          # NEAR smart contract
└── docs/
    ├── README.md         # User and bookkeeper guide
    └── DEVELOPERS.md     # Technical documentation
```

This is a high-level representation of the repository.

## Getting started

PayFlow consists of independently run frontend and backend services.

1. Set up PostgreSQL.
2. Configure the backend environment.
3. Apply the required SQL schema and migrations.
4. Start the FastAPI backend.
5. Configure the frontend API URL.
6. Start the Next.js frontend.
7. Connect a NEAR testnet wallet.

See the [Developer Documentation](docs/DEVELOPERS.md) for setup and configuration details.

## Documentation

- [User Guide — Freelancers, Clients and Bookkeepers](docs/README.md)
- [Developer Documentation](docs/DEVELOPERS.md)

## Limitations

- This is a testnet prototype, not a production financial service.
- The current payment integration uses Tidepool sandbox.
- Official 1Click API integration remains future work.
- Supported assets and networks depend on provider availability.
- Mainnet deployment and production security review remain future work.
- Testnet assets do not represent real-world funds.

## Hackathon Track

Built for the NEAR hackathon **Real-World Money** track (`realworld`).

**PayFlow — make crypto payments fit the invoice, not the other way around.**