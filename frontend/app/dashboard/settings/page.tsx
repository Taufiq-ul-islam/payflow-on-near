"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

type AuthUser = {
  authenticated: boolean;
  account_id: string;
};

export default function SettingsPage() {
  const [accountId, setAccountId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadAccount() {
      try {
        const user = await apiRequest<AuthUser>("/auth/me");

        if (!cancelled) {
          setAccountId(user.account_id);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error
              ? err.message
              : "Could not load your authenticated account"
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadAccount();

    return () => {
      cancelled = true;
    };
  }, []);

  async function copyAccount() {
    if (!accountId) return;

    try {
      await navigator.clipboard.writeText(accountId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      window.prompt("Copy your NEAR account ID:", accountId);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-7">
      <div>
        <p className="text-sm text-slate-400">Workspace / Settings</p>
        <h1 className="mt-1 text-3xl font-bold">Settings</h1>
        <p className="mt-2 text-sm text-slate-500">
          Review your PayFlow environment and settlement configuration.
        </p>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-semibold">Settlement account</h2>
        <p className="mt-1 text-sm text-slate-500">
          Your authenticated NEAR account receives invoice payments.
        </p>

        <div className="mt-5">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            NEAR account ID
          </label>

          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <div className="min-w-0 flex-1 break-all rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
              {loading
                ? "Loading account..."
                : error
                  ? "Unavailable"
                  : accountId}
            </div>

            <button
              onClick={copyAccount}
              disabled={!accountId || loading}
              className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>

          {error && (
            <p className="mt-2 text-sm text-rose-600">{error}</p>
          )}

          <p className="mt-2 text-xs text-slate-400">
            This account ID is obtained from your authenticated PayFlow
            session, not from frontend configuration.
          </p>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-6">
        <h2 className="font-semibold">Network configuration</h2>

        <div className="mt-5 grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400">NEAR network</p>
            <p className="mt-2 font-semibold">Testnet</p>
          </div>

          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400">Settlement asset</p>
            <p className="mt-2 font-semibold">USDC</p>
          </div>

          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400">Cross-chain provider</p>
            <p className="mt-2 font-semibold">Tidepool 1Click</p>
          </div>

          <div className="rounded-xl bg-slate-50 p-4">
            <p className="text-xs text-slate-400">Gas sponsorship</p>
            <p className="mt-2 font-semibold">Relayer integration pending</p>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-amber-200 bg-amber-50 p-5">
        <h2 className="font-semibold text-amber-900">Development mode</h2>
        <p className="mt-2 text-sm leading-6 text-amber-800">
          PayFlow is currently configured for testnet development. Do not use
          real funds or production credentials.
        </p>
      </section>
    </div>
  );
}