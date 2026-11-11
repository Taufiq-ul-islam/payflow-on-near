"use client";

import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { Client } from "@/lib/types";

export default function ClientsPage() {
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");

  async function loadClients() {
    try {
      setLoading(true);
      setError("");

      const result = await apiRequest<Client[]>("/clients/");

      setClients(Array.isArray(result) ? result : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load clients");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadClients();
  }, []);

  async function addClient(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setSaving(true);
      setError("");

      const createdClient = await apiRequest<Client>("/clients/",
        {
          method: "POST",
          body: JSON.stringify({
            name,
            email,
            company: company || null,
          }),
        }
      );

      // Immediately display the successfully created client.
      setClients((previous) => [
        createdClient,
        ...previous.filter((client) => client.id !== createdClient.id),
      ]);

      // Clear the form only after successful creation.
      setName("");
      setEmail("");
      setCompany("");

      // Refresh separately. A refresh failure must not undo creation.
      try {
        await loadClients();
      } catch {
        // loadClients handles its own errors.
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not add client"
      );
    } finally {
      setSaving(false);
    }
  }

  async function deleteClient(clientId: string) {
    if (!window.confirm("Delete this saved client?")) return;

    try {
      await apiRequest(`/clients/${clientId}`, { method: "DELETE" });

      setClients((previous) =>
        previous.filter((client) => client.id !== clientId)
      );
    } catch (err) {
      alert(err instanceof Error ? err.message : "Could not delete client");
    }
  }

  return (
    <div className="space-y-7">
      <div>
        <p className="text-sm text-slate-400">Workspace / Clients</p>
        <h1 className="mt-1 text-3xl font-bold">Clients</h1>
        <p className="mt-2 text-sm text-slate-500">
          Keep your client details ready for your next invoice.
        </p>
      </div>

      {error && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          {error}
        </div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-semibold">Add a client</h2>

        <form onSubmit={addClient} className="mt-5 grid gap-3 md:grid-cols-3">
          <input
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Client name"
            className="rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-slate-400"
          />
          <input
            required
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Email address"
            className="rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-slate-400"
          />
          <input
            value={company}
            onChange={(event) => setCompany(event.target.value)}
            placeholder="Company (optional)"
            className="rounded-xl border border-slate-200 px-4 py-3 text-sm outline-none focus:border-slate-400"
          />

          <div className="md:col-span-3">
            <button
              disabled={saving}
              className="rounded-xl bg-slate-950 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
            >
              {saving ? "Saving..." : "Add client"}
            </button>
          </div>
        </form>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="border-b border-slate-100 px-6 py-5">
          <h2 className="font-semibold">Saved clients</h2>
          <p className="mt-1 text-xs text-slate-400">
            {clients.length} client{clients.length === 1 ? "" : "s"}
          </p>
        </div>

        {loading ? (
          <p className="p-8 text-sm text-slate-400">Loading clients...</p>
        ) : clients.length === 0 ? (
          <p className="p-8 text-center text-sm text-slate-500">
            No saved clients yet.
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {clients.map((client) => (
              <div
                key={client.id}
                className="flex flex-col justify-between gap-3 px-6 py-5 sm:flex-row sm:items-center"
              >
                <div className="min-w-0">
                  <p className="font-semibold">{client.name}</p>
                  <p className="mt-1 text-sm text-slate-500">
                    {client.email}
                  </p>
                  <p className="mt-1 text-xs text-slate-400">
                    {client.company || "No company"} · Added{" "}
                    {formatDate(client.created_at)}
                  </p>
                </div>

                <button
                  onClick={() => deleteClient(client.id)}
                  className="self-start rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-500 hover:border-rose-200 hover:text-rose-600 sm:self-center"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}