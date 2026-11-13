# PayFlow — Judge Demo Guide

## 1. One-sentence pitch

**PayFlow lets a freelancer invoice in dollars, share one link, and accept crypto payments without making the client learn the freelancer's preferred chain or token.**

## 2. What NEAR enables

NEAR contributes three concrete capabilities:

1. **USDC settlement destination:** PayFlow uses a NEAR account and NEP-141 USDC as the freelancer's settlement destination for direct NEAR payments and the configured cross-chain provider route.
2. **Cross-chain payment abstraction:** NEAR Intents-style routing/provider integration lets the payer start with a supported source asset while PayFlow tracks settlement to the freelancer's configured destination asset. The current implementation uses the official NEAR Intents 1Click API on NEAR mainnet for cross-chain routing.
3. **Gas-sponsored contract interaction:** NEP-366 meta-transactions plus Pagoda Relayer let PayFlow's backend submit the allowed `record_settlement` contract call and pay its gas, so the freelancer does not need to hold NEAR merely to record the PayFlow settlement attestation.


## 3. Demo preparation

- Start PostgreSQL, backend, frontend and Pagoda Relayer.
- Confirm `GET http://localhost:8000/health` returns `{"status":"healthy"}`.
- Confirm the PayFlow contract and admin function-call key point to the intended NEAR mainnet deployment.
- Confirm the relayer mainnet account has sufficient NEAR for sponsored contract calls.
- Confirm `RELAYER_URL=http://127.0.0.1:3030`.
- Confirm `NEAR_INTENTS_BASE_URL=https://1click.chaindefuser.com` and that the configured credential is for the official 1Click API.
- Use a deliberately small invoice amount for any live-value demonstration.
- Have a payer NEAR mainnet wallet with the configured NEAR USDC asset.
- Open two browser tabs: freelancer dashboard and public payer link.
- Keep a backup screen recording in case a public RPC or the 1Click API is slow.

## 4. Important technical honesty

- The current implementation targets NEAR mainnet and the official NEAR Intents 1Click API. The earlier Tidepool testnet prototype is part of the project development history, not the active provider configuration.
- Cross-chain routing is configured against the official 1Click mainnet API. Keep provider credentials, network settings and asset IDs aligned with mainnet.
- The direct NEAR USDC flow verifies the NEAR transaction and NEP-141 transfer event via NEAR RPC.
- Cross-chain settlement depends on the provider's status and transaction evidence.
- PayFlow's contract records a settlement attestation after backend reconciliation. It does not independently prove the foreign-chain swap.
- Refunds are separate records; the original payment history is retained.

## 5. Suggested demo narration

"Freelancers shouldn't need to send wallet addresses, explain bridges, or reconcile a pile of unrelated transactions just to get paid. They create a normal USD invoice and share a link. The payer chooses an available crypto route. PayFlow tracks the attempt and settlement, then keeps the invoice, payment and refund records separate for bookkeeping. NEAR gives us the USDC settlement destination, a standard NEP-141 transfer interface, and NEP-366 meta-transactions so our allowed settlement-recording call can be sponsored by Pagoda Relayer. The freelancer can focus on the invoice, not gas management."
