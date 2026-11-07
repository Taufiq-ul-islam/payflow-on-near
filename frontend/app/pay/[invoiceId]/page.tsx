"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";

import { apiRequest } from "@/lib/api";
import { formatCurrency, formatDate, shortAddress } from "@/lib/format";
import type { Invoice, PaymentStatus } from "@/lib/types";
import StatusBadge from "@/components/ui/status-badge";

interface TidepoolToken {
  assetId: string;
  decimals: number;
  blockchain: string;
  symbol: string;
  price: number;
  contractAddress?: string;
}

interface QuoteResponse {
  correlationId?: string;
  signature?: string;
  quoteRequest?: {
    amount?: string;
    originAsset?: string;
    destinationAsset?: string;
    recipient?: string;
  };
  quote?: {
    depositAddress?: string;
    depositMemo?: string;
    amountIn?: string;
    amountOut?: string;
    minAmountIn?: string;
    timeEstimate?: number;
  };
}

interface CommittedAttempt {
  payment_attempt_id: string;
  status: string;
  deposit_address: string;
  deposit_memo?: string | null;
  expected_amount: string;
  destination_asset: string;
  quote: QuoteResponse;
}

function PublicPaymentPageContent() {
  const params = useParams<{ invoiceId: string }>();
  const invoiceId = params.invoiceId;

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [tokens, setTokens] = useState<TidepoolToken[]>([]);
  const [selectedAsset, setSelectedAsset] = useState("");
  const [refundAddress, setRefundAddress] = useState("");

  const [quote, setQuote] = useState<QuoteResponse | null>(null);
  const [attempt, setAttempt] = useState<CommittedAttempt | null>(null);

  const [txHash, setTxHash] = useState("");
  const [paymentStatus, setPaymentStatus] = useState<PaymentStatus | string>("PENDING_DEPOSIT");

  const [loading, setLoading] = useState(true);
  const [quoting, setQuoting] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [checking, setChecking] = useState(false);

  const [idempotencyKey] = useState(() => crypto.randomUUID());

  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);

        const [invoiceData, tokenData] = await Promise.all([
          apiRequest<Invoice>(`/invoices/${invoiceId}`),
          apiRequest<TidepoolToken[]>("/payments/tokens"),
        ]);

        setInvoice(invoiceData);
        setTokens(Array.isArray(tokenData) ? tokenData : []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load invoice"
        );
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [invoiceId]);

  const selectedToken = useMemo(
    () => tokens.find((token) => token.assetId === selectedAsset),
    [tokens, selectedAsset]
  );

  async function requestQuote() {
    if (!selectedAsset || !refundAddress.trim()) {
      setError("Select a token and enter a refund address.");
      return;
    }

    try {
      setQuoting(true);
      setError("");
      setQuote(null);
      setAttempt(null);

      const query = new URLSearchParams({
        source_asset: selectedAsset,
        refund_address: refundAddress.trim(),
      });

      const result = await apiRequest<QuoteResponse>(
        `/payments/quote/${invoiceId}?${query.toString()}`,
        { method: "POST" }
      );

      setQuote(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Quote request failed");
    } finally {
      setQuoting(false);
    }
  }

  async function commitQuote() {
    if (!selectedAsset || !refundAddress.trim()) return;

    try {
      setCommitting(true);
      setError("");

      const query = new URLSearchParams({
        source_asset: selectedAsset,
        refund_address: refundAddress.trim(),
      });

      const result = await apiRequest<CommittedAttempt>(
        `/payments/commit/${invoiceId}?${query.toString()}`,
        {
          method: "POST",
          headers: {
            "Idempotency-Key": idempotencyKey,
          },
        }
      );

      setAttempt(result);
      setPaymentStatus(result.status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create payment");
    } finally {
      setCommitting(false);
    }
  }

  async function submitDeposit() {
    if (!attempt || !txHash.trim()) {
      setError("Enter the source-chain transaction hash.");
      return;
    }

    try {
      setSubmitting(true);
      setError("");

      await apiRequest(
        `/payments/${attempt.payment_attempt_id}/deposit-submit`,
        {
          method: "POST",
          body: JSON.stringify({
            tx_hash: txHash.trim(),
          }),
        }
      );

      await checkStatus();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not submit transaction"
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function checkStatus() {
    if (!attempt) return;

    try {
      setChecking(true);
      setError("");

      const result = await apiRequest<{
        provider_status: string;
        invoice_status: string;
      }>(`/payments/${attempt.payment_attempt_id}/status`);

      setPaymentStatus(result.provider_status);
      setInvoice((previous) =>
        previous
          ? { ...previous, status: result.invoice_status as Invoice["status"] }
          : previous
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not check payment status"
      );
    } finally {
      setChecking(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <p className="text-sm text-slate-500">Loading invoice...</p>
      </main>
    );
  }

  if (!invoice || error && !invoice) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50 p-6">
        <div className="max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center">
          <h1 className="text-xl font-bold">Invoice unavailable</h1>
          <p className="mt-2 text-sm text-slate-500">
            {error || "This invoice could not be found."}
          </p>
        </div>
      </main>
    );
  }

  const payable = invoice.status === "PENDING";

  return (
    <main className="min-h-screen bg-[#f7f8fa] px-4 py-10 text-slate-900">
      <div className="mx-auto max-w-2xl">
        <div className="mb-8 text-center">
          <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-2xl bg-slate-950 font-bold text-white">
            P
          </div>
          <h1 className="mt-3 text-xl font-bold">PayFlow</h1>
          <p className="mt-1 text-sm text-slate-400">
            Simple payments, across chains.
          </p>
        </div>

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 p-6 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Invoice {invoice.invoice_number}
                </p>
                <h2 className="mt-3 text-4xl font-bold tracking-tight">
                  {formatCurrency(invoice.total, invoice.currency)}
                </h2>
                <p className="mt-2 text-sm text-slate-500">
                  Billed to {invoice.client_name}
                </p>
              </div>

              <StatusBadge status={invoice.status} />
            </div>

            <div className="mt-6 flex justify-between border-t border-slate-100 pt-4 text-sm">
              <span className="text-slate-400">Due date</span>
              <span className="font-medium">
                {formatDate(invoice.due_date)}
              </span>
            </div>
          </div>

          <div className="p-6 sm:p-8">
            <h3 className="font-semibold">Invoice summary</h3>

            <div className="mt-4 space-y-3">
              {invoice.items?.map((item, index) => (
                <div
                  key={item.id ?? index}
                  className="flex justify-between gap-4 text-sm"
                >
                  <div>
                    <p className="font-medium">{item.description}</p>
                    <p className="mt-1 text-xs text-slate-400">
                      {item.quantity} ×{" "}
                      {formatCurrency(item.unit_price, invoice.currency)}
                    </p>
                  </div>
                  <p className="font-semibold">
                    {formatCurrency(
                      Number(item.quantity) * Number(item.unit_price),
                      invoice.currency
                    )}
                  </p>
                </div>
              ))}
            </div>

            <div className="mt-5 flex justify-between border-t border-slate-100 pt-5">
              <span className="font-semibold">Total</span>
              <span className="text-lg font-bold">
                {formatCurrency(invoice.total, invoice.currency)}
              </span>
            </div>
          </div>
        </section>

        {!payable && (
          <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 text-center">
            <h3 className="font-semibold">
              {invoice.status === "PAID"
                ? "This invoice has been paid"
                : "This invoice is no longer payable"}
            </h3>
            <p className="mt-2 text-sm text-slate-500">
              Contact the freelancer if you believe this is incorrect.
            </p>
          </div>
        )}

        {payable && (
          <section className="mt-5 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Secure checkout
              </p>
              <h2 className="mt-1 text-xl font-bold">
                Pay with your preferred token
              </h2>
              <p className="mt-2 text-sm leading-6 text-slate-500">
                Choose a supported asset. PayFlow routes the payment and targets USDC settlement for the freelancer.
              </p>
            </div>

            {!attempt && (
              <>
                <label className="mt-6 block text-sm font-semibold">
                  Payment token
                  <select
                    value={selectedAsset}
                    onChange={(event) => {
                      setSelectedAsset(event.target.value);
                      setQuote(null);
                    }}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-normal outline-none focus:border-slate-400"
                  >
                    <option value="">Choose a supported token</option>
                    {tokens.map((token) => (
                      <option key={token.assetId} value={token.assetId}>
                        {token.symbol} · {token.blockchain.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>

                {selectedToken && (
                  <p className="mt-2 text-xs text-slate-400">
                    {selectedToken.symbol} · {selectedToken.decimals} decimals ·{" "}
                    {selectedToken.assetId}
                  </p>
                )}

                <label className="mt-5 block text-sm font-semibold">
                  Refund address
                  <input
                    value={refundAddress}
                    onChange={(event) => setRefundAddress(event.target.value)}
                    placeholder="Your wallet address on the selected source chain"
                    className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-slate-400"
                  />
                  <span className="mt-2 block text-xs font-normal text-slate-400">
                    Used only if the swap needs to refund your payment.
                  </span>
                </label>

                <button
                  disabled={!selectedAsset || !refundAddress.trim() || quoting}
                  onClick={requestQuote}
                  className="mt-6 w-full rounded-xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                >
                  {quoting ? "Getting quote..." : "Get payment quote"}
                </button>

                {quote && (
                  <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
                    <p className="font-semibold">Quote preview</p>
                    <div className="mt-3 space-y-2 text-sm">
                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">You pay</span>
                        <span className="font-semibold">
                          {quote.quote?.amountIn || "—"} {selectedToken?.symbol}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">Freelancer receives</span>
                        <span className="font-semibold">
                          {quote.quote?.amountOut || "—"} USDC
                        </span>
                      </div>
                    </div>

                    <button
                      onClick={commitQuote}
                      disabled={committing}
                      className="mt-5 w-full rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:opacity-40"
                    >
                      {committing ? "Preparing payment..." : "Continue to payment"}
                    </button>
                  </div>
                )}
              </>
            )}

            {attempt && (
              <div className="mt-6 space-y-5">
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-amber-900">
                      Payment address created
                    </p>
                    <StatusBadge status={paymentStatus} />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-amber-800">
                    Send the quoted amount of your selected token to the address below using the correct source network.
                  </p>
                </div>

                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                    Deposit address
                  </p>
                  <div className="mt-2 break-all rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-sm">
                    {attempt.deposit_address}
                  </div>
                  <button
                    onClick={() =>
                      navigator.clipboard.writeText(attempt.deposit_address)
                    }
                    className="mt-2 text-xs font-semibold text-slate-600 hover:text-slate-950"
                  >
                    Copy address
                  </button>
                </div>

                {attempt.deposit_memo && (
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Required memo
                    </p>
                    <div className="mt-2 break-all rounded-xl border border-slate-200 bg-slate-50 p-4 font-mono text-sm">
                      {attempt.deposit_memo}
                    </div>
                  </div>
                )}

                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs text-slate-400">Expected deposit amount</p>
                  <p className="mt-1 text-xl font-bold">
                    {attempt.quote.quote?.amountIn || attempt.expected_amount}
                  </p>
                  <p className="mt-1 break-all text-xs text-slate-400">
                    {attempt.quote.quoteRequest?.originAsset}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-semibold">
                    Source transaction hash
                    <input
                      value={txHash}
                      onChange={(event) => setTxHash(event.target.value)}
                      placeholder="Paste your transaction hash"
                      className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-mono text-sm font-normal outline-none focus:border-slate-400"
                    />
                  </label>

                  <button
                    onClick={submitDeposit}
                    disabled={!txHash.trim() || submitting}
                    className="mt-3 w-full rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:opacity-40"
                  >
                    {submitting ? "Submitting..." : "Submit transaction hash"}
                  </button>
                </div>

                <button
                  onClick={checkStatus}
                  disabled={checking}
                  className="w-full rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold hover:bg-slate-50 disabled:opacity-40"
                >
                  {checking ? "Checking..." : "Check payment status"}
                </button>

                {paymentStatus === "SUCCESS" && (
                  <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-medium text-emerald-800">
                    Payment successfully settled. Thank you!
                  </div>
                )}
              </div>
            )}
          </section>
        )}

        {error && (
          <div className="mt-5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {error}
          </div>
        )}

        <p className="mt-6 text-center text-xs leading-5 text-slate-400">
          Powered by PayFlow · Testnet assets have no monetary value.
        </p>
      </div>
    </main>
  );
}

export default function PublicPaymentPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen flex items-center justify-center">
          Loading payment page...
        </div>
      }
    >
      <PublicPaymentPageContent />
    </Suspense>
  );
}