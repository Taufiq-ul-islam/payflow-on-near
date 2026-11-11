"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { apiRequest, downloadCsv } from "@/lib/api";
import { formatCurrency, formatDate } from "@/lib/format";
import type { Invoice } from "@/lib/types";
import StatusBadge from "@/components/ui/status-badge";

export default function InvoicesPage() {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadInvoices() {
    try {
      setLoading(true);
      setError("");

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

  useEffect(() => {
    loadInvoices();
  }, []);

  const filtered = useMemo(() => {
    return invoices.filter((invoice) => {
      const matchesStatus =
        filter === "ALL" || invoice.status === filter;

      const term = search.toLowerCase();

      const matchesSearch =
        invoice.invoice_number.toLowerCase().includes(term) ||
        invoice.client_name.toLowerCase().includes(term);

      return matchesStatus && matchesSearch;
    });
  }, [invoices, filter, search]);

  async function exportCsv() {
    try {
      await downloadCsv(`/reports/invoices/csv`, "payflow-invoices.csv");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Export failed");
    }
  }

  return (
    <div className="space-y-7">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm text-slate-400">Workspace / Invoices</p>
          <h1 className="mt-1 text-3xl font-bold">Invoices</h1>
          <p className="mt-2 text-sm text-slate-500">
            Create, share and track your invoices.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={exportCsv}
            className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold hover:bg-slate-50"
          >
            Export CSV
          </button>
          <Link
            href="/dashboard/invoices/new"
            className="rounded-xl bg-slate-950 px-4 py-3 text-sm font-semibold text-white hover:bg-slate-800"
          >
            + New invoice
          </Link>
        </div>
      </div>

      <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-4 sm:flex-row">
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder="Search invoice number or client..."
          className="min-w-0 flex-1 rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-slate-400"
        />

        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          className="rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none"
        >
          <option value="ALL">All statuses</option>
          <option value="PENDING">Pending</option>
          <option value="PAID">Paid</option>
          <option value="CANCELLED">Cancelled</option>
          <option value="EXPIRED">Expired</option>
        </select>
      </div>

      {error && (
        <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
          {error}
          <p className="mt-1 text-xs">
            This page requires the backend GET /invoices/ list endpoint.
          </p>
        </div>
      )}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-4">
          <p className="text-sm font-semibold">
            {filtered.length} invoice{filtered.length === 1 ? "" : "s"}
          </p>
          <button
            onClick={loadInvoices}
            className="text-xs font-semibold text-slate-500 hover:text-slate-900"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <p className="p-8 text-sm text-slate-400">Loading invoices...</p>
        ) : filtered.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <p className="font-semibold">No matching invoices</p>
            <p className="mt-2 text-sm text-slate-500">
              Try another search or create a new invoice.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-6 py-4 font-semibold">Invoice</th>
                  <th className="px-6 py-4 font-semibold">Client</th>
                  <th className="px-6 py-4 font-semibold">Due date</th>
                  <th className="px-6 py-4 font-semibold">Amount</th>
                  <th className="px-6 py-4 font-semibold">Status</th>
                  <th className="px-6 py-4"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((invoice) => (
                  <tr
                    key={invoice.id}
                    className="border-t border-slate-100 hover:bg-slate-50"
                  >
                    <td className="px-6 py-4 font-semibold">
                      {invoice.invoice_number}
                    </td>
                    <td className="px-6 py-4">
                      <p className="font-medium">{invoice.client_name}</p>
                      <p className="mt-1 text-xs text-slate-400">
                        {invoice.client_email}
                      </p>
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
                    <td className="px-6 py-4 text-right">
                      <Link
                        href={`/dashboard/invoices/${invoice.id}`}
                        className="font-semibold text-slate-600 hover:text-slate-950"
                      >
                        View →
                      </Link>
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