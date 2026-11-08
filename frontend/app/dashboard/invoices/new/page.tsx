"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { apiRequest, DEMO_FREELANCER_ID } from "@/lib/api";
import { formatCurrency } from "@/lib/format";
import type { Client } from "@/lib/types";

interface Item {
  description: string;
  quantity: string;
  unit_price: string;
}

export default function NewInvoicePage() {
  const router = useRouter();

  const [clients, setClients] = useState<Client[]>([]);
  const [clientsLoading, setClientsLoading] = useState(true);
  const [clientLoadError, setClientLoadError] = useState("");
  const [selectedClientId, setSelectedClientId] = useState("");

  const [clientName, setClientName] = useState("");
  const [clientEmail, setClientEmail] = useState("");
  const [dueDate, setDueDate] = useState("");

  const [items, setItems] = useState<Item[]>([
    { description: "", quantity: "1", unit_price: "" },
  ]);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadClients() {
      try {
        setClientsLoading(true);
        setClientLoadError("");

        const params = new URLSearchParams({
          freelancer_id: DEMO_FREELANCER_ID,
        });

        const result = await apiRequest<Client[]>(
          `/clients/?${params.toString()}`
        );

        setClients(Array.isArray(result) ? result : []);
      } catch (err) {
        setClientLoadError(
          err instanceof Error ? err.message : "Could not load saved clients."
        );
      } finally {
        setClientsLoading(false);
      }
    }

    loadClients();
  }, []);

  function handleClientSelect(clientId: string) {
    setSelectedClientId(clientId);

    if (!clientId) return;

    const selectedClient = clients.find(
      (client) => client.id === clientId
    );

    if (selectedClient) {
      setClientName(selectedClient.name);
      setClientEmail(selectedClient.email);
    }
  }

  const total = useMemo(
    () =>
      items.reduce(
        (sum, item) =>
          sum +
          (Number(item.quantity) || 0) *
            (Number(item.unit_price) || 0),
        0
      ),
    [items]
  );

  function updateItem(
    index: number,
    field: keyof Item,
    value: string
  ) {
    setItems((previous) =>
      previous.map((item, itemIndex) =>
        itemIndex === index
          ? { ...item, [field]: value }
          : item
      )
    );
  }

  function addItem() {
    setItems((previous) => [
      ...previous,
      { description: "", quantity: "1", unit_price: "" },
    ]);
  }

  function removeItem(index: number) {
    setItems((previous) =>
      previous.filter((_, itemIndex) => itemIndex !== index)
    );
  }

  async function submitInvoice(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!clientName.trim() || !clientEmail.trim()) {
      setError("Enter the client's name and email.");
      return;
    }

    if (
      items.some(
        (item) =>
          !item.description.trim() ||
          Number(item.quantity) <= 0 ||
          Number(item.unit_price) < 0 ||
          item.unit_price === ""
      )
    ) {
      setError(
        "Check each line item. Quantity must be positive and price cannot be negative."
      );
      return;
    }

    if (total <= 0) {
      setError("Invoice total must be greater than zero.");
      return;
    }

    try {
      setLoading(true);

      const result = await apiRequest<{ id: string }>("/invoices/", {
        method: "POST",
        body: JSON.stringify({
          freelancer_id: DEMO_FREELANCER_ID,
          client_name: clientName.trim(),
          client_email: clientEmail.trim(),
          due_date: dueDate ? `${dueDate}T23:59:59Z` : null,
          items: items.map((item) => ({
            description: item.description.trim(),
            quantity: item.quantity,
            unit_price: item.unit_price,
          })),
        }),
      });

      router.push(`/dashboard/invoices/${result.id}`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to create invoice"
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-7">
      <div>
        <Link
          href="/dashboard/invoices"
          className="text-sm text-slate-400 hover:text-slate-700"
        >
          ← Back to invoices
        </Link>
        <h1 className="mt-3 text-3xl font-bold">Create invoice</h1>
        <p className="mt-2 text-sm text-slate-500">
          Add your client's details and the work you're billing for.
        </p>
      </div>

      <form onSubmit={submitInvoice} className="space-y-6">
        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="font-semibold">Client details</h2>
              <p className="mt-1 text-xs text-slate-500">
                Select a saved client or enter their details manually.
              </p>
            </div>

            <Link
              href="/dashboard/clients"
              className="text-sm font-semibold text-slate-700 hover:text-slate-950"
            >
              + Manage clients
            </Link>
          </div>

          <div className="mt-5">
            <label className="text-sm font-medium">
              Select saved client

              <select
                value={selectedClientId}
                onChange={(event) =>
                  handleClientSelect(event.target.value)
                }
                disabled={clientsLoading || clients.length === 0}
                className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 font-normal outline-none focus:border-slate-400 disabled:bg-slate-50 disabled:text-slate-400"
              >
                <option value="">
                  {clientsLoading
                    ? "Loading clients..."
                    : clients.length === 0
                      ? "No saved clients available"
                      : "Choose a client (optional)"}
                </option>

                {clients.map((client) => (
                  <option key={client.id} value={client.id}>
                    {client.name} ({client.email})
                  </option>
                ))}
              </select>
            </label>

            {!clientsLoading && clients.length === 0 && (
              <p className="mt-2 text-xs text-slate-500">
                You haven't saved any clients yet.{" "}
                <Link
                  href="/dashboard/clients"
                  className="font-semibold text-slate-800 underline"
                >
                  Add a client
                </Link>
                {" "}or enter their details below.
              </p>
            )}

            {clientLoadError && (
              <p className="mt-2 text-xs text-rose-600">
                Could not load saved clients: {clientLoadError}. You can
                still enter client details manually.
              </p>
            )}
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="text-sm font-medium">
              Client name
              <input
                required
                value={clientName}
                onChange={(event) => setClientName(event.target.value)}
                placeholder="Acme Studio"
                className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-slate-400"
              />
            </label>

            <label className="text-sm font-medium">
              Client email
              <input
                required
                type="email"
                value={clientEmail}
                onChange={(event) => setClientEmail(event.target.value)}
                placeholder="client@example.com"
                className="mt-2 w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-slate-400"
              />
            </label>

            <label className="text-sm font-medium sm:col-span-2">
              Due date
              <input
                type="date"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
                className="mt-2 block w-full rounded-xl border border-slate-200 px-4 py-3 font-normal outline-none focus:border-slate-400 sm:max-w-xs"
              />
            </label>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-semibold">Line items</h2>
              <p className="mt-1 text-xs text-slate-400">
                Invoice amounts are denominated in USD.
              </p>
            </div>

            <button
              type="button"
              onClick={addItem}
              className="text-sm font-semibold text-slate-700 hover:text-slate-950"
            >
              + Add item
            </button>
          </div>

          <div className="mt-5 space-y-4">
            {items.map((item, index) => (
              <div
                key={index}
                className="grid gap-3 rounded-xl bg-slate-50 p-4 sm:grid-cols-[minmax(0,1fr)_100px_130px_32px]"
              >
                <label className="text-xs font-semibold text-slate-500">
                  Description
                  <input
                    required
                    value={item.description}
                    onChange={(event) =>
                      updateItem(index, "description", event.target.value)
                    }
                    placeholder="Website design"
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 outline-none focus:border-slate-400"
                  />
                </label>

                <label className="text-xs font-semibold text-slate-500">
                  Quantity
                  <input
                    required
                    type="number"
                    min="0.0001"
                    step="0.0001"
                    value={item.quantity}
                    onChange={(event) =>
                      updateItem(index, "quantity", event.target.value)
                    }
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 outline-none focus:border-slate-400"
                  />
                </label>

                <label className="text-xs font-semibold text-slate-500">
                  Unit price
                  <input
                    required
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.unit_price}
                    onChange={(event) =>
                      updateItem(index, "unit_price", event.target.value)
                    }
                    placeholder="0.00"
                    className="mt-2 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-normal text-slate-900 outline-none focus:border-slate-400"
                  />
                </label>

                <button
                  type="button"
                  disabled={items.length === 1}
                  onClick={() => removeItem(index)}
                  aria-label="Remove line item"
                  className="mt-6 h-8 rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-30"
                >
                  ×
                </button>
              </div>
            ))}
          </div>

          <div className="mt-6 flex items-center justify-between border-t border-slate-100 pt-5">
            <span className="text-sm font-semibold text-slate-500">
              Total due
            </span>
            <span className="text-2xl font-bold">
              {formatCurrency(total)}
            </span>
          </div>
        </section>

        {error && (
          <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
            {error}
          </div>
        )}

        <div className="flex flex-col-reverse justify-end gap-3 sm:flex-row">
          <Link
            href="/dashboard/invoices"
            className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-center text-sm font-semibold hover:bg-slate-50"
          >
            Cancel
          </Link>

          <button
            type="submit"
            disabled={loading}
            className="rounded-xl bg-slate-950 px-6 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {loading ? "Creating invoice..." : "Create invoice"}
          </button>
        </div>
      </form>
    </div>
  );
}
