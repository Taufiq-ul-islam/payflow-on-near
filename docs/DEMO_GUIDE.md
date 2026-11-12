# PayFlow — Judge Demo Guide

## 1. One-sentence pitch

**PayFlow lets a freelancer invoice in dollars, share one link, and accept crypto payments without making the client learn the freelancer's preferred chain or token.**

## 2. What NEAR enables — say this, not "powered by NEAR"

NEAR contributes three concrete capabilities:

1. **USDC settlement destination:** PayFlow uses a NEAR account and NEP-141 USDC as the freelancer's settlement destination for direct NEAR payments and the configured cross-chain provider route.
2. **Cross-chain payment abstraction:** NEAR Intents-style routing/provider integration lets the payer start with a supported source asset while PayFlow tracks settlement to the freelancer's configured destination asset. In the current testnet demo this is exercised through Tidepool sandbox; do not call it a live mainnet 1Click integration.
3. **Gas-sponsored contract interaction:** NEP-366 meta-transactions plus Pagoda Relayer let PayFlow's backend submit the allowed `record_settlement` contract call and pay its gas, so the freelancer does not need to hold NEAR merely to record the PayFlow settlement attestation.

Also mention **NEP-141**: it gives the project a standard fungible-token interface and transfer event format that the backend can verify for direct NEAR USDC transfers.

### The 20-second version

"NEAR gives PayFlow the settlement rail and the gasless contract interaction. The client can pay from a supported crypto route; the freelancer tracks a dollar invoice and receives the configured USDC settlement on NEAR. NEP-366 and Pagoda Relayer sponsor our restricted settlement-recording call, so the freelancer doesn't need NEAR for that bookkeeping action."

## 3. 90-second live demo

| Time | Do | Judge should see |
|---|---|---|
| 0:00–0:10 | Open PayFlow and explain the invoice problem | USD-first freelancer workflow |
| 0:10–0:20 | Connect freelancer NEAR testnet wallet | Wallet-based login; no password |
| 0:20–0:35 | Create a USD invoice with due date and line item | Invoice number, total, pending status |
| 0:35–0:45 | Copy/open public payment link in payer tab | Public invoice page with amount and pay action |
| 0:45–1:05 | Complete a small direct NEAR USDC payment | Wallet transaction, pending-to-paid status, transaction link |
| 1:05–1:15 | Open freelancer dashboard/payment history | Successful payment and received amount |
| 1:15–1:25 | Show contract settlement record / relayer evidence | NEP-366 relayed `record_settlement` action |
| 1:25–1:30 | Show CSV export | Downloadable invoice ledger |

A cross-chain payment and refund can be shown as a longer technical walkthrough if provider sandbox and test assets are ready. Do not risk the core demo on an unavailable external token route.

## 4. Demo preparation

- Start PostgreSQL, backend, frontend and Pagoda Relayer.
- Confirm `GET http://localhost:8000/health` returns `{"status":"healthy"}`.
- Confirm the PayFlow contract and admin IDs point to testnet deployments.
- Confirm the relayer testnet account has enough test NEAR.
- Confirm `RELAYER_URL=http://127.0.0.1:3030`.
- Confirm the provider base URL matches the Tidepool sandbox API being used.
- Use a small invoice (USD 1.00 is enough for the direct USDC test).
- Have a payer NEAR testnet wallet with the configured test USDC.
- Open two browser tabs: freelancer dashboard and public payer link.
- Keep a backup screen recording in case a public RPC or sandbox provider is slow.

## 5. Important technical honesty

- Current working prototype is testnet + Tidepool sandbox.
- NEAR Intents currently has no testnet according to the hackathon's HACKATHON.md. The official instructions say Intents use requires mainnet, separate development accounts, tiny amounts and `dry: true` quotes. The current testnet flow must not be represented as a mainnet 1Click API integration.
- The direct NEAR USDC flow verifies the NEAR transaction and NEP-141 transfer event via NEAR RPC.
- Cross-chain settlement depends on the provider's status and transaction evidence.
- PayFlow's contract records a settlement attestation after backend reconciliation. It does not independently prove the foreign-chain swap.
- Refunds are separate records; the original payment history is retained.

## 6. Suggested demo narration

"Freelancers shouldn't need to send wallet addresses, explain bridges, or reconcile a pile of unrelated transactions just to get paid. They create a normal USD invoice and share a link. The payer chooses an available crypto route. PayFlow tracks the attempt and settlement, then keeps the invoice, payment and refund records separate for bookkeeping. NEAR gives us the USDC settlement destination, a standard NEP-141 transfer interface, and NEP-366 meta-transactions so our allowed settlement-recording call can be sponsored by Pagoda Relayer. The freelancer can focus on the invoice, not gas management."

## 7. X demo post checklist

The NEAR Hackathon asks the human to publish a public X post that:
- says the project was built at NEAR HACKATHON;
- tags `@NEARProtocol` and `#NEARHackathon`;
- includes the demo video or screenshots;
- leads with the user problem;
- shows one complete user action and visible result;
- explains exactly what NEAR enables;
- links to the public repository and invites specific feedback.

The human publishes the post and supplies its URL. Do not post on the user's behalf.
