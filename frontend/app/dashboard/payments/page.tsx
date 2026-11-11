
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import {
  apiRequest,
  getRefunds,
  getRefund,
  createRefundQuote,
  approveRefund,
  submitRefundDeposit,
  reconcileRefund,
} from "@/lib/api";

import { getCurrentUser } from "@/lib/auth";
import { sendNearUsdcTransfer } from "@/lib/near-transfer";
import {
  formatDateTime,
  shortAddress,
  formatTokenAmount,
} from "@/lib/format";

import type { PaymentAttempt, Refund } from "@/lib/types";

import StatusBadge from "@/components/ui/status-badge";

const NEAR_USDC_CONTRACT = "usdc.tidepool-sandbox.testnet";
const NEAR_USDC_DECIMALS = 6;

function decimalToBaseUnits(value: string, decimals: number): string {
  const match = /^(\d+)(?:\.(\d*))?$/.exec(value.trim());

  if (!match) {
    throw new Error("Invalid USDC amount.");
  }

  const whole = match[1];
  const fraction = match[2] ?? "";

  if (
    fraction.length > decimals &&
    /[1-9]/.test(fraction.slice(decimals))
  ) {
    throw new Error(
      `Amount supports at most ${decimals} decimal places.`
    );
  }

  const normalized = fraction
    .slice(0, decimals)
    .padEnd(decimals, "0");

  return (
    BigInt(whole) * 10n ** BigInt(decimals) +
    BigInt(normalized || "0")
  ).toString();
}

function extractTransactionHash(result: unknown): string {
  if (!result || typeof result !== "object") {
    throw new Error(
      "The wallet returned an unexpected transaction result. Check your wallet activity for the transaction hash."
    );
  }

  const outcome = result as {
    transaction?: { hash?: string };
    transaction_outcome?: { id?: string };
  };

  const hash =
    outcome.transaction?.hash ||
    outcome.transaction_outcome?.id;

  if (!hash || typeof hash !== "string") {
    throw new Error(
      "Could not extract the NEAR transaction hash. Check your wallet activity before retrying."
    );
  }

  return hash;
}

function normalizeRefunds(refundList: Refund[]): Refund[] {
  return refundList.map((refund) => ({
    ...refund,
    id: refund.id || refund.refund_id || "",
  }));
}

export default function PaymentsPage() {
  const [payments, setPayments] = useState<PaymentAttempt[]>([]);
  const [refunds, setRefunds] = useState<Refund[]>([]);
  const [accountId, setAccountId] = useState("");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedPayment, setSelectedPayment] =
    useState<PaymentAttempt | null>(null);

  const [refundQuote, setRefundQuote] =
    useState<Refund | null>(null);

  const [refundError, setRefundError] = useState("");
  const [refundSuccess, setRefundSuccess] = useState("");

  const [quoting, setQuoting] = useState(false);
  const [loadingRefundDetails, setLoadingRefundDetails] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [reconcilingId, setReconcilingId] = useState("");

  const [pendingSubmissions, setPendingSubmissions] =
    useState<Record<string, string>>({});

  const [retryingRefundId, setRetryingRefundId] = useState("");

  function savePendingSubmission(refundId: string, txHash: string) {
    setPendingSubmissions((current) => ({
      ...current,
      [refundId]: txHash,
    }));

    try {
      const stored = JSON.parse(
        sessionStorage.getItem("payflow_pending_refunds") || "{}"
      );

      stored[refundId] = txHash;

      sessionStorage.setItem(
        "payflow_pending_refunds",
        JSON.stringify(stored)
      );
    } catch {
      // In-memory state still supports retry during this page session.
    }
  }

  function clearPendingSubmission(refundId: string) {
    setPendingSubmissions((current) => {
      const updated = { ...current };
      delete updated[refundId];
      return updated;
    });

    try {
      const stored = JSON.parse(
        sessionStorage.getItem("payflow_pending_refunds") || "{}"
      );

      delete stored[refundId];

      sessionStorage.setItem(
        "payflow_pending_refunds",
        JSON.stringify(stored)
      );
    } catch {
      // The backend remains the source of truth.
    }
  }

  async function recoverPendingSubmissions(refundList: Refund[]) {
    try {
      const stored = JSON.parse(
        sessionStorage.getItem("payflow_pending_refunds") || "{}"
      );

      const recovered: Record<string, string> = {
        ...(stored && typeof stored === "object" ? stored : {}),
      };

      const processingRefunds = refundList.filter(
        (refund) =>
          ["PROCESSING", "REVIEW", "PENDING", "FAILED"].includes(
            refund.status
          )
      );

      await Promise.all(
        processingRefunds.map(async (refund) => {
          try {
            const detailedRefund = await getRefund(refund.id);

            const transaction = detailedRefund.transactions?.find(
              (item) =>
                item.transaction_type === "REFUND_DEPOSIT" ||
                item.transaction_type === "DIRECT_NEAR_REFUND"
            );

            if (transaction?.tx_hash) {
              recovered[refund.id] = transaction.tx_hash;
            }
          } catch {
            // Preserve any locally stored hash if detail retrieval fails.
          }
        })
      );

      setPendingSubmissions(recovered);

      sessionStorage.setItem(
        "payflow_pending_refunds",
        JSON.stringify(recovered)
      );
    } catch {
      // Recovery is best-effort; normal page loading must continue.
    }
  }

  async function loadPayments() {
    try {
      setLoading(true);
      setError("");

      const [paymentData, refundData, user] = await Promise.all([
        apiRequest<PaymentAttempt[]>("/payments/"),
        getRefunds(),
        getCurrentUser(),
      ]);

      setPayments(
        Array.isArray(paymentData) ? paymentData : []
      );

      const normalizedRefunds = normalizeRefunds(
        Array.isArray(refundData) ? refundData : []
      );

      setRefunds(normalizedRefunds);
      await recoverPendingSubmissions(normalizedRefunds);

      setAccountId(user.account_id || "");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not load payment activity."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPayments();
  }, []);

  function openRefund(payment: PaymentAttempt) {
    setSelectedPayment(payment);
    setRefundQuote(null);
    setRefundError("");
    setRefundSuccess("");

    if (!payment.payer_address || !payment.payer_network) {
      setRefundError(
        "This payment does not have the original payer wallet and network saved. A safe automatic refund cannot be created."
      );
    }
  }

  async function openExistingRefund(
    payment: PaymentAttempt,
    refund: Refund
  ) {
    setSelectedPayment(payment);
    setRefundQuote(null);
    setRefundError("");
    setRefundSuccess("");
    setLoadingRefundDetails(true);

    try {
      const detail = await getRefund(refund.id);
      setRefundQuote(detail);
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not load the existing refund."
      );
    } finally {
      setLoadingRefundDetails(false);
    }
  }

  function closeRefund() {
    if (processing || quoting || loadingRefundDetails) return;

    setSelectedPayment(null);
    setRefundQuote(null);
    setRefundError("");
    setRefundSuccess("");
  }

  async function requestRefundQuote() {
    if (!selectedPayment) return;

    if (
      !selectedPayment.payer_address ||
      !selectedPayment.payer_network
    ) {
      setRefundError(
        "The original payer wallet and network are missing from this payment."
      );
      return;
    }

    try {
      setQuoting(true);
      setRefundError("");
      setRefundSuccess("");
      setRefundQuote(null);

      const paymentAttemptId =
        selectedPayment.payment_attempt_id ||
        selectedPayment.id;

      // Destination, USDC asset, and refundable amount are derived
      // by the backend from the saved original payer details.
      const quote = await createRefundQuote(
        paymentAttemptId,
        crypto.randomUUID()
      );

      if (!quote.id) {
        throw new Error("The refund quote did not return a refund ID.");
      }

      setRefundQuote(quote);
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not create refund quote."
      );
    } finally {
      setQuoting(false);
    }
  }

  async function refreshRefundHistory(): Promise<Refund[]> {
    try {
      const result = await getRefunds();
      const normalized = normalizeRefunds(result);

      setRefunds(normalized);
      return normalized;
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not refresh refund history."
      );

      return [];
    }
  }

  async function approveAndSendRefund() {
    if (!refundQuote) return;

    if (refundQuote.status !== "AWAITING_APPROVAL") {
      setRefundError(
        "This refund is no longer awaiting approval. Use its existing transaction to retry submission or reconcile it."
      );
      return;
    }

    if (!accountId) {
      setRefundError(
        "Your authenticated NEAR account could not be found."
      );
      return;
    }

    if (pendingSubmissions[refundQuote.id]) {
      setRefundError(
        "A wallet transaction already exists for this refund. Use Retry submission instead of sending another transfer."
      );
      return;
    }

    let approvedRefundId = refundQuote.id;

    try {
      setProcessing(true);
      setRefundError("");
      setRefundSuccess("");

      const approved = await approveRefund(refundQuote.id);
      approvedRefundId = approved.id || approved.refund_id || "";

      if (!approvedRefundId) {
        throw new Error(
          "The approved refund did not return a valid refund ID."
        );
      }

      const receiverId =
        approved.destination_network === "near"
          ? approved.destination_address
          : approved.deposit_address;

      if (!receiverId) {
        throw new Error(
          "The approved refund has no valid transfer destination."
        );
      }

      const amount = decimalToBaseUnits(
        approved.source_amount,
        NEAR_USDC_DECIMALS
      );

      const transferResult = await sendNearUsdcTransfer({
        accountId,
        tokenContractId: NEAR_USDC_CONTRACT,
        receiverId,
        amount,
        registerReceiver: approved.destination_network !== "near",
      });

      const txHash = extractTransactionHash(transferResult);

      // Persist immediately, before making another API request.
      savePendingSubmission(approvedRefundId, txHash);

      setRefundSuccess(
        `Wallet transfer completed. Transaction: ${txHash}`
      );

      await submitRefundDeposit(approvedRefundId, {
        tx_hash: txHash,
        near_sender_account: accountId,
      });

      setRefundSuccess(
        `Transaction submitted successfully. Hash: ${txHash}`
      );

      // Reconciliation is separate from transaction submission.
      try {
        await reconcileRefund(approvedRefundId);
      } catch {
        // Keep the recorded hash; reconciliation can be retried separately.
      }

      const updatedRefunds = await refreshRefundHistory();
      const updatedRefund = updatedRefunds.find(
        (refund) => refund.id === approvedRefundId
      );

      if (updatedRefund?.status === "SUCCESS") {
        clearPendingSubmission(approvedRefundId);

        setRefundSuccess(
          `Refund completed successfully. Transaction: ${txHash}`
        );

        setRefundQuote(null);
      } else {
        setRefundSuccess(
          `Transaction submitted. Refund status is ${updatedRefund?.status || "PROCESSING"}. You can reconcile or retry submission using the existing transaction hash.`
        );
      }
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not complete the refund transfer."
      );

      // Do not clear the saved hash. It may be needed for safe recovery.
    } finally {
      setProcessing(false);
    }
  }

  async function retryRefundSubmission(refundId: string) {
    const txHash = pendingSubmissions[refundId];

    if (!txHash) {
      setRefundError(
        "No saved transaction hash is available. Do not send another transfer until you verify the original wallet transaction."
      );
      return;
    }

    if (!accountId) {
      setRefundError(
        "Your authenticated NEAR account could not be found."
      );
      return;
    }

    try {
      setRetryingRefundId(refundId);
      setRefundError("");

      // Reuse the original hash. Never initiate another wallet transfer here.
      await submitRefundDeposit(refundId, {
        tx_hash: txHash,
        near_sender_account: accountId,
      });

      try {
        await reconcileRefund(refundId);
      } catch {
        // Refund may still be processing.
      }

      const updatedRefunds = await refreshRefundHistory();
      const updatedRefund = updatedRefunds.find(
        (refund) => refund.id === refundId
      );

      if (updatedRefund?.status === "SUCCESS") {
        clearPendingSubmission(refundId);
      }
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not retry refund submission."
      );
    } finally {
      setRetryingRefundId("");
    }
  }

  async function reconcileExistingRefund(refundId: string) {
    try {
      setReconcilingId(refundId);
      setRefundError("");

      await reconcileRefund(refundId);

      const updatedRefunds = await refreshRefundHistory();
      const updatedRefund = updatedRefunds.find(
        (refund) => refund.id === refundId
      );

      if (updatedRefund?.status === "SUCCESS") {
        clearPendingSubmission(refundId);
      }
    } catch (err) {
      setRefundError(
        err instanceof Error
          ? err.message
          : "Could not reconcile refund."
      );
    } finally {
      setReconcilingId("");
    }
  }

  function canRefund(payment: PaymentAttempt) {
    const status = String(payment.status);

    return (
      status === "SUCCESS" ||
      status === "DUPLICATE_SETTLEMENT"
    );
  }

  function latestRefundForPayment(
    payment: PaymentAttempt
  ): Refund | undefined {
    const paymentAttemptId =
      payment.payment_attempt_id || payment.id;

    return refunds
      .filter(
        (refund) =>
          refund.payment_attempt_id === paymentAttemptId
      )
      .sort(
        (a, b) =>
          new Date(b.created_at || 0).getTime() -
          new Date(a.created_at || 0).getTime()
      )[0];
  }

  return (
    <div className="space-y-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm text-slate-400">
            Workspace / Payments
          </p>

          <h1 className="mt-1 text-3xl font-bold">
            Payments
          </h1>

          <p className="mt-2 text-sm text-slate-500">
            Track cross-chain payment attempts, settlements, and refunds.
          </p>
        </div>

        <button
          onClick={loadPayments}
          disabled={loading}
          className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold hover:bg-slate-50 disabled:opacity-50"
        >
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
        </div>
      )}

      {refundError && !selectedPayment && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {refundError}
        </div>
      )}

      {/* Payment activity */}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="font-semibold">
            Payment activity
          </h2>

          <p className="mt-1 text-xs text-slate-400">
            {payments.length} payment attempt
            {payments.length === 1 ? "" : "s"}
          </p>
        </div>

        {loading ? (
          <p className="p-8 text-sm text-slate-400">
            Loading payments...
          </p>
        ) : payments.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <p className="font-semibold">
              No payment activity yet
            </p>

            <p className="mt-2 text-sm text-slate-500">
              Payment attempts will appear here after a client starts paying an invoice.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[850px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-6 py-4 font-semibold">
                    Payment
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Invoice
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Destination
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Received
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Status
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Created
                  </th>

                  <th className="px-6 py-4 font-semibold">
                    Action
                  </th>
                </tr>
              </thead>

              <tbody>
                {payments.map((payment) => (
                  <tr
                    key={
                      payment.id ||
                      payment.payment_attempt_id
                    }
                    className="border-t border-slate-100"
                  >
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">
                      {shortAddress(
                        payment.id ||
                        payment.payment_attempt_id
                      )}
                    </td>

                    <td className="px-6 py-4">
                      {payment.invoice_number || (
                        <Link
                          href={`/dashboard/invoices/${payment.invoice_id}`}
                          className="font-semibold hover:underline"
                        >
                          View invoice
                        </Link>
                      )}
                    </td>

                    <td className="px-6 py-4 text-slate-500">
                      {payment.destination_asset || "USDC"}
                    </td>

                    <td className="px-6 py-4 font-semibold">
                      {payment.received_amount != null
                        ? `${formatTokenAmount(
                            String(payment.received_amount),
                            6,
                            6
                          )} USDC`
                        : "—"}
                    </td>

                    <td className="px-6 py-4">
                      <StatusBadge status={payment.status} />
                    </td>

                    <td className="px-6 py-4 text-xs text-slate-500">
                      {formatDateTime(payment.created_at)}
                    </td>

                    <td className="px-6 py-4">
                      {(() => {
                        const existingRefund =
                          latestRefundForPayment(payment);

                        if (existingRefund) {
                          return (
                            <button
                              onClick={() =>
                                openExistingRefund(
                                  payment,
                                  existingRefund
                                )
                              }
                              className="font-mono text-xs font-semibold text-blue-700 hover:underline"
                              title={`Open refund ${existingRefund.id}`}
                            >
                              {shortAddress(existingRefund.id)}
                            </button>
                          );
                        }

                        return canRefund(payment) ? (
                          <button
                            onClick={() => openRefund(payment)}
                            className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold hover:bg-slate-50"
                          >
                            Refund
                          </button>
                        ) : (
                          <span className="text-xs text-slate-300">
                            —
                          </span>
                        );
                      })()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Refund quote and approval */}

      {selectedPayment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto bg-slate-950/50 p-4">
          <div className="my-auto w-full max-w-xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
              <div>
                <h2 className="text-xl font-bold">
                  Refund payment
                </h2>

                <p className="mt-1 text-xs text-slate-400">
                  Payment{" "}
                  {shortAddress(
                    selectedPayment.payment_attempt_id ||
                    selectedPayment.id
                  )}
                </p>
              </div>

              <button
                onClick={closeRefund}
                disabled={
                  processing ||
                  quoting ||
                  loadingRefundDetails
                }
                className="rounded-lg px-3 py-1 text-xl text-slate-400 hover:bg-slate-100 disabled:opacity-40"
                aria-label="Close refund dialog"
              >
                ×
              </button>
            </div>

            <div className="space-y-5 px-6 py-6">
              {refundError && (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                  {refundError}
                </div>
              )}

              {refundSuccess && (
                <div className="break-all rounded-xl border border-green-200 bg-green-50 p-3 text-sm text-green-800">
                  {refundSuccess}
                </div>
              )}

              {loadingRefundDetails ? (
                <p className="py-8 text-center text-sm text-slate-500">
                  Loading existing refund...
                </p>
              ) : !refundQuote ? (
                <>
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                      Original payer details
                    </p>

                    <div className="mt-3 space-y-3 text-sm">
                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          Original network
                        </span>

                        <span className="font-semibold uppercase">
                          {selectedPayment.payer_network || "Unavailable"}
                        </span>
                      </div>

                      <div>
                        <p className="text-slate-500">
                          Refund destination
                        </p>

                        <p className="mt-1 break-all font-mono text-xs">
                          {selectedPayment.payer_address || "Unavailable"}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                    The refund will be sent as USDC to the original payer wallet on the original payment network. The backend calculates the remaining refundable amount and selects the destination USDC asset automatically.
                  </div>

                  <button
                    onClick={requestRefundQuote}
                    disabled={
                      quoting ||
                      !selectedPayment.payer_address ||
                      !selectedPayment.payer_network
                    }
                    className="w-full rounded-xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                  >
                    {quoting
                      ? "Getting refund quote..."
                      : "Get refund quote"}
                  </button>
                </>
              ) : (
                <>
                  <div className="rounded-xl border border-slate-200 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                        Refund details
                      </p>

                      <StatusBadge status={refundQuote.status} />
                    </div>

                    <div className="mt-4 space-y-3 text-sm">
                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          Refund ID
                        </span>

                        <span className="font-mono text-xs font-semibold">
                          {shortAddress(refundQuote.id)}
                        </span>
                      </div>

                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          Destination network
                        </span>

                        <span className="font-semibold uppercase">
                          {refundQuote.destination_network}
                        </span>
                      </div>

                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          Refund amount
                        </span>

                        <span className="font-semibold">
                          {refundQuote.requested_amount} USDC
                        </span>
                      </div>

                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          NEAR USDC required
                        </span>

                        <span className="font-semibold">
                          {refundQuote.source_amount} USDC
                        </span>
                      </div>

                      <div className="flex justify-between gap-4">
                        <span className="text-slate-500">
                          Expected destination amount
                        </span>

                        <span className="font-semibold">
                          {refundQuote.expected_amount} USDC
                        </span>
                      </div>

                      <div className="border-t border-slate-100 pt-3">
                        <p className="text-xs text-slate-500">
                          Destination address
                        </p>

                        <p className="mt-1 break-all font-mono text-xs">
                          {refundQuote.destination_address}
                        </p>
                      </div>

                      {refundQuote.fee_details && (
                        <details className="border-t border-slate-100 pt-3">
                          <summary className="cursor-pointer text-xs font-semibold text-slate-600">
                            Fee details
                          </summary>

                          <pre className="mt-3 overflow-x-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                            {JSON.stringify(
                              refundQuote.fee_details,
                              null,
                              2
                            )}
                          </pre>
                        </details>
                      )}
                    </div>
                  </div>

                  {refundQuote.status === "AWAITING_APPROVAL" && (
                    <>
                      <div className="rounded-xl bg-slate-50 p-4 text-xs leading-5 text-slate-600">
                        Approval initiates a NEAR USDC transfer from your connected wallet.
                        {refundQuote.destination_network === "near"
                          ? " The transfer goes directly to the original payer's NEAR account."
                          : " The transfer goes to the Tidepool deposit address for cross-chain settlement."}
                        {" "}Review the amount, fees, and destination before continuing.
                      </div>

                      <button
                        onClick={approveAndSendRefund}
                        disabled={
                          processing ||
                          !!pendingSubmissions[refundQuote.id]
                        }
                        className="w-full rounded-xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-40"
                      >
                        {processing
                          ? "Processing wallet transfer..."
                          : "Approve and send refund"}
                      </button>
                    </>
                  )}

                  {pendingSubmissions[refundQuote.id] && (
                    <button
                      onClick={() =>
                        retryRefundSubmission(refundQuote.id)
                      }
                      disabled={!!retryingRefundId}
                      className="w-full rounded-xl border border-amber-300 bg-amber-50 px-5 py-3.5 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-40"
                    >
                      {retryingRefundId === refundQuote.id
                        ? "Retrying submission..."
                        : "Retry submission using existing transaction"}
                    </button>
                  )}

                  {(
                    ["PROCESSING", "REVIEW", "PENDING"].includes(
                      refundQuote.status
                    ) ||
                    (
                      refundQuote.status === "FAILED" &&
                      (refundQuote.transactions?.length ?? 0) > 0
                    )
                  ) && (
                    <button
                      onClick={() =>
                        reconcileExistingRefund(refundQuote.id)
                      }
                      disabled={reconcilingId === refundQuote.id}
                      className="w-full rounded-xl border border-slate-200 px-5 py-3.5 text-sm font-semibold hover:bg-slate-50 disabled:opacity-40"
                    >
                      {reconcilingId === refundQuote.id
                        ? "Checking..."
                        : "Reconcile refund"}
                    </button>
                  )}

                  {refundQuote.status === "FAILED" &&
                    (refundQuote.transactions?.length ?? 0) === 0 && (
                      <button
                        onClick={() => {
                          setRefundQuote(null);
                          setRefundError("");
                          setRefundSuccess("");
                        }}
                        className="w-full rounded-xl bg-slate-950 px-5 py-3.5 text-sm font-semibold text-white hover:bg-slate-800"
                      >
                        Get a new refund quote
                      </button>
                    )}

                  {refundQuote.status === "SUCCESS" && (
                    <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-sm text-green-800">
                      This refund has been completed successfully.
                    </div>
                  )}

                  {refundQuote.status === "SUCCESS" &&
                    !pendingSubmissions[refundQuote.id] && (
                      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                        This refund has been approved. Check its existing transaction before taking further action. Do not initiate another wallet transfer.
                      </div>
                    )}

                  <button
                    onClick={closeRefund}
                    disabled={processing || quoting}
                    className="w-full rounded-xl border border-slate-200 px-5 py-3 text-sm font-semibold hover:bg-slate-50 disabled:opacity-40"
                  >
                    Close
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
