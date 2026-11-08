"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiRequest, DEMO_FREELANCER_ID } from "@/lib/api";
import { formatDateTime, shortAddress, formatTokenAmount } from "@/lib/format";
import type { PaymentAttempt } from "@/lib/types";
import StatusBadge from "@/components/ui/status-badge";

export default function PaymentsPage() {
  const [payments, setPayments] = useState<PaymentAttempt[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadPayments() {
    try {
      setLoading(true);
      setError("");

      const params = new URLSearchParams({
        freelancer_id: DEMO_FREELANCER_ID,
      });

      const result = await apiRequest<PaymentAttempt[]>(
        `/payments/?${params.toString()}`
      );

      setPayments(Array.isArray(result) ? result : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not load payments"
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPayments();
  }, []);

  return (
    <div className="space-y-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm text-slate-400">Workspace / Payments</p>
          <h1 className="mt-1 text-3xl font-bold">Payments</h1>
          <p className="mt-2 text-sm text-slate-500">
            Track cross-chain payment attempts and settlements.
          </p>
        </div>

        <button
          onClick={loadPayments}
          className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold hover:bg-slate-50"
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
          <p className="mt-1 text-xs">
            Payment history requires the backend GET /payments/ endpoint.
          </p>
        </div>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="font-semibold">Payment activity</h2>
          <p className="mt-1 text-xs text-slate-400">
            {payments.length} payment attempt{payments.length === 1 ? "" : "s"}
          </p>
        </div>

        {loading ? (
          <p className="p-8 text-sm text-slate-400">Loading payments...</p>
        ) : payments.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <p className="font-semibold">No payment activity yet</p>
            <p className="mt-2 text-sm text-slate-500">
              Payment attempts will appear here after a client starts paying an invoice.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-6 py-4 font-semibold">Payment</th>
                  <th className="px-6 py-4 font-semibold">Invoice</th>
                  <th className="px-6 py-4 font-semibold">Destination</th>
                  <th className="px-6 py-4 font-semibold">Received</th>
                  <th className="px-6 py-4 font-semibold">Status</th>
                  <th className="px-6 py-4 font-semibold">Created</th>
                </tr>
              </thead>
              <tbody>
                {payments.map((payment) => (
                  <tr
                    key={payment.id || payment.payment_attempt_id}
                    className="border-t border-slate-100"
                  >
                    <td className="px-6 py-4 font-mono text-xs text-slate-500">
                      {shortAddress(payment.id || payment.payment_attempt_id)}
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
                        ? `${formatTokenAmount(String(payment.received_amount), 6, 6)} USDC`
                        : "—"}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={payment.status} />
                    </td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      {formatDateTime(payment.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}