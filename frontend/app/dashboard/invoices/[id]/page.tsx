"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Invoice } from "@/lib/types";
import StatusBadge from "@/components/ui/status-badge";

export default function InvoiceDetailsPage() {
  const params = useParams<{ id: string }>();
  const invoiceId = params.id;

  const [invoice, setInvoice] = useState<Invoice | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const result = await apiRequest<Invoice>(
          `/invoices/${invoiceId}`
        );
        setInvoice(result);
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

  async function copyPaymentLink() {
    const url = `${window.location.origin}/pay/${invoiceId}`;

    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      alert(url);
    }
  }

  if (loading) {
    return <p className="text-sm text-slate-400">Loading invoice...</p>;
  }

  if (error || !invoice) {
    return (
      <div className="rounded-2xl border border-rose-200 bg-rose-50 p-6 text-sm text-rose-700">
        {error || "Invoice not found"}
        <div className="mt-4">
          <Link href="/dashboard/invoices" className="font-semibold underline">
            Back to invoices
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <Link
            href="/dashboard/invoices"
            className="text-sm text-slate-400 hover:text-slate-700"
          >
            ← Back to invoices
          </Link>
          <h1 className="mt-3 text-3xl font-bold">
            {invoice.invoice_number}
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Invoice details and payment status.
          </p>
        </div>

        <StatusBadge status={invoice.status} />
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-6 md:p-8">
        <div className="flex flex-col justify-between gap-6 border-b border-slate-100 pb-7 sm:flex-row">
          <div>
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Bill to
            </p>
            <h2 className="mt-2 text-lg font-bold">
              {invoice.client_name}
            </h2>
            {invoice.client_email && (
              <p className="mt-1 text-sm text-slate-500">
                {invoice.client_email}
              </p>
            )}
          </div>

          <div className="sm:text-right">
            <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">
              Invoice total
            </p>
            <p className="mt-2 text-3xl font-bold tracking-tight">
              {formatCurrency(invoice.total, invoice.currency)}
            </p>
            <p className="mt-2 text-sm text-slate-500">
              Due {formatDate(invoice.due_date)}
            </p>
          </div>
        </div>

        <div className="mt-7">
          <h3 className="font-semibold">Line items</h3>

          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="py-3 font-semibold">Description</th>
                  <th className="py-3 text-right font-semibold">Quantity</th>
                  <th className="py-3 text-right font-semibold">Unit price</th>
                  <th className="py-3 text-right font-semibold">Total</th>
                </tr>
              </thead>
              <tbody>
                {invoice.items?.map((item, index) => (
                  <tr key={item.id ?? index} className="border-t border-slate-100">
                    <td className="py-4 font-medium">{item.description}</td>
                    <td className="py-4 text-right text-slate-500">
                      {item.quantity}
                    </td>
                    <td className="py-4 text-right text-slate-500">
                      {formatCurrency(item.unit_price, invoice.currency)}
                    </td>
                    <td className="py-4 text-right font-semibold">
                      {formatCurrency(
                        Number(item.quantity) * Number(item.unit_price),
                        invoice.currency
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {invoice.status === "PENDING" && (
        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
            <div>
              <h2 className="font-semibold">Share payment link</h2>
              <p className="mt-1 text-sm text-slate-500">
                Your client can open this link to pay using a supported token.
              </p>
            </div>

            <button
              onClick={copyPaymentLink}
              className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
            >
              {copied ? "Copied!" : "Copy payment link"}
            </button>
          </div>

          <div className="mt-4 break-all rounded-xl bg-slate-50 p-3 text-sm text-slate-500">
            {typeof window !== "undefined"
              ? `${window.location.origin}/pay/${invoiceId}`
              : `/pay/${invoiceId}`}
          </div>
        </section>
      )}

      {invoice.status === "PAID" && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5 text-sm text-emerald-800">
          This invoice is marked as paid.
        </div>
      )}
    </div>
  );
}