# PayFlow — User Guide

PayFlow is designed for freelancers who want to invoice in dollars without making clients learn cryptocurrency first.

A freelancer creates an invoice in **USD** and shares a payment link. The client opens the link and pays using an asset and network currently supported by the official **NEAR Intents 1Click API**. The intended freelancer settlement asset is **USDC on NEAR**.

This guide explains how freelancers, clients, and bookkeepers can use PayFlow.

## 1. For Freelancers

### Creating an invoice

1. Sign in using your NEAR wallet.
2. Open the invoice creation page.
3. Enter the invoice and client details.
4. Add the line items, due date, and invoice amount.
5. Create the invoice.
6. Share the generated payment link with your client.

Invoices are denominated in USD so the commercial amount remains clear even when the client pays using cryptocurrency.

### Sharing a payment link

Every invoice has a public payment page. Share this link with your client instead of manually sending wallet addresses or payment instructions. The client can review the invoice and select an available payment option.

### Tracking payments

Use the dashboard to monitor invoice and payment activity. PayFlow maintains separate invoice and payment records so payment attempts can be tracked without losing the original invoice history. A payment may take time to complete while provider and blockchain transactions are confirmed.

## 2. For Clients

### Paying an invoice

1. Open the payment link received from the freelancer.
2. Review the invoice details and USD amount.
3. Select an available payment asset and network.
4. Follow the 1Click deposit instructions.
5. Wait for the payment status to update.

Available payment options depend on the official 1Click token registry and current provider availability.

### What does the freelancer receive?

PayFlow is designed around USDC settlement on NEAR. The asset used by the client to pay may differ from the settlement asset received by the freelancer.

## 3. Refunds

PayFlow maintains separate refund records linked to the original payment. This preserves the original payment history while allowing refunds to be tracked independently. The implemented refund paths are:

- Direct NEAR USDC refund.
- Cross-chain refund through the official NEAR Intents 1Click API.

Refunds may pass through approval and processing before being marked successful. A refund marked as processing should not be considered complete until its destination transaction has been confirmed and reconciled.

## 4. For Bookkeepers

PayFlow maintains invoice and payment information to help freelancers review their financial activity. Where CSV export is available, records can be exported for spreadsheet and bookkeeping workflows.

| Term | Meaning |
|---|---|
| Invoice amount | The commercial amount charged to the client, denominated in USD |
| Payment amount | The amount transferred by the client |
| Settlement amount | The amount received in the configured settlement asset |
| Payment attempt | An individual attempt to pay an invoice |
| Refund | A separate record linked to an original payment |
| Transaction reference | The blockchain transaction hash or provider reference |

The original payment record is not erased when a refund is issued. Always reconcile exported records with final payment/refund statuses and transaction references before using them as formal accounting evidence.

## 5. Understanding statuses

PayFlow tracks invoice, payment, and refund lifecycles separately.

| Record | Status | Meaning |
|---|---|---|
| Invoice | Pending | Awaiting payment |
| Invoice | Paid | Payment successfully settled |
| Invoice | Cancelled | Invoice is no longer active |
| Invoice | Expired | Invoice has passed its validity period |
| Payment | Pending | Payment flow has started |
| Payment | Processing | Payment is being processed or confirmed |
| Payment | Success | Settlement has been confirmed |
| Payment | Failed | Payment did not complete |
| Payment | Duplicate settlement / Review | An additional or unexpected settlement requires separate handling |
| Refund | Awaiting approval | Refund quote is waiting for approval |
| Refund | Processing | Refund has been submitted and is awaiting completion |
| Refund | Success | Refund has been confirmed |
| Refund | Failed / Review | Refund requires investigation or did not complete |

The application and API may use more specific internal status names.

## 6. Network and provider information

The current integration targets NEAR mainnet and the official NEAR Intents 1Click API (`https://1click.chaindefuser.com`). Direct NEAR transfers are verified through NEAR RPC. The earlier testnet prototype used the Tidepool sandbox; that historical work is acknowledged in the repository README.

PayFlow is a project prototype, not a complete accounting, custody, or regulated payment service. Supported assets and networks depend on provider availability.

## 7. Developer documentation

For technical setup, architecture, environment configuration, API details, database design, and payment/refund implementation, see [DEVELOPERS.md](DEVELOPERS.md).
