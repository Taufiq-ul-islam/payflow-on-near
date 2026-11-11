"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Invoice } from "@/lib/types";
import StatusBadge from "@/components/ui/status-badge";

export default function DashboardPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function load() {
      try {
        const result = await apiRequest<Invoice[]>("/invoices/");

        setInvoices(Array.isArray(result) ? result : []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Could not load invoices"
        );
      } finally {
        setLoading(false);
      }
    }

    load();
  }, []);

  const paid = invoices.filter((item) => item.status === "PAID");
  const pending = invoices.filter((item) => item.status === "PENDING");

  const totalPaid = paid.reduce(
    (sum, item) => sum + Number(item.total || 0), 0
  );

  const totalPending = pending.reduce(
    (sum, item) => sum + Number(item.total || 0), 0
  );

  const totalInvoiced = invoices.reduce(
    (sum, item) => sum + Number(item.total || 0), 0
  );

  const stats = [
    {
      label: "Total invoiced",
      value: formatCurrency(totalInvoiced),
      note: `${invoices.length} invoices`,
    },
    {
      label: "Total received",
      value: formatCurrency(totalPaid),
      note: `${paid.length} paid invoices`,
    },
    {
      label: "Awaiting payment",
      value: formatCurrency(totalPending),
      note: `${pending.length} pending invoices`,
    },
  ];

  return (
    <div className="space-y-8">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-slate-400">
            Overview
          </p>
          <h1 className="mt-1 text-3xl font-bold tracking-tight">
            Good to see you.
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            Here's what's happening with your invoices.
          </p>
        </div>

        <Link
          href="/dashboard/invoices/new"
          className="inline-flex items-center justify-center rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
        >
          + Create invoice
        </Link>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          Could not load dashboard data: {error}
          <p className="mt-1 text-xs">
            The invoice-list endpoint needs to be enabled in the backend.
          </p>
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-3">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-2xl border border-slate-200 bg-white p-6"
          >
            <p className="text-sm text-slate-500">{stat.label}</p>
            <p className="mt-3 text-2xl font-bold tracking-tight">
              {loading ? "—" : stat.value}
            </p>
            <p className="mt-2 text-xs text-slate-400">{stat.note}</p>
          </div>
        ))}
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <h2 className="font-semibold">Recent invoices</h2>
            <p className="mt-1 text-xs text-slate-400">
              Your latest billing activity
            </p>
          </div>
          <Link
            href="/dashboard/invoices"
            className="text-sm font-semibold text-slate-600 hover:text-slate-950"
          >
            View all →
          </Link>
        </div>

        {loading ? (
          <p className="p-8 text-sm text-slate-400">Loading invoices...</p>
        ) : invoices.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <p className="font-semibold">No invoices yet</p>
            <p className="mt-2 text-sm text-slate-500">
              Create your first invoice to get started.
            </p>
            <Link
              href="/dashboard/invoices/new"
              className="mt-5 inline-flex rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white"
            >
              Create invoice
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-6 py-3 font-semibold">Invoice</th>
                  <th className="px-6 py-3 font-semibold">Client</th>
                  <th className="px-6 py-3 font-semibold">Due date</th>
                  <th className="px-6 py-3 font-semibold">Amount</th>
                  <th className="px-6 py-3 font-semibold">Status</th>
                </tr>
              </thead>
              <tbody>
                {invoices.slice(0, 5).map((invoice) => (
                  <tr
                    key={invoice.id}
                    className="border-t border-slate-100 hover:bg-slate-50"
                  >
                    <td className="px-6 py-4">
                      <Link
                        href={`/dashboard/invoices/${invoice.id}`}
                        className="font-semibold hover:underline"
                      >
                        {invoice.invoice_number}
                      </Link>
                    </td>
                    <td className="px-6 py-4 text-slate-600">
                      {invoice.client_name}
                    </td>
                    <td className="px-6 py-4 text-slate-500">
                      {formatDate(invoice.due_date)}
                    </td>
                    <td className="px-6 py-4 font-semibold">
                      {formatCurrency(invoice.total, invoice.currency)}
                    </td>
                    <td className="px-6 py-4">
                      <StatusBadge status={invoice.status} />
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