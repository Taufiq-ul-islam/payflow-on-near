"use client";

import { useState } from "react";
import { DEMO_FREELANCER_ID } from "@/lib/api";

export default function SettingsPage() {
  const [copied, setCopied] = useState(false);

  async function copyAccount() {
    try {
      await navigator.clipboard.writeText(DEMO_FREELANCER_ID);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      alert(DEMO_FREELANCER_ID);
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
          Your configured NEAR account is the recipient of invoice payments.
        </p>

        <div className="mt-5">
          <label className="text-xs font-semibold uppercase tracking-wide text-slate-400">
            NEAR account ID
          </label>
          <div className="mt-2 flex flex-col gap-2 sm:flex-row">
            <div className="min-w-0 flex-1 break-all rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
              {DEMO_FREELANCER_ID}
            </div>
            <button
              onClick={copyAccount}
              className="rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold hover:bg-slate-50"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="mt-2 text-xs text-slate-400">
            Development configuration. Account registration and editing will be connected to authentication later.
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
          PayFlow is currently configured for testnet development. Do not use real funds or production credentials. Authentication, wallet registration and persistent user settings are not enabled yet.
        </p>
      </section>
    </div>
  );
}