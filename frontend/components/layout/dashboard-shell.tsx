"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const navigation = [
  {
    label: "Overview",
    href: "/dashboard",
    icon: "◫",
  },
  {
    label: "Invoices",
    href: "/dashboard/invoices",
    icon: "▤",
  },
  {
    label: "Payments",
    href: "/dashboard/payments",
    icon: "⇄",
  },
  {
    label: "Clients",
    href: "/dashboard/clients",
    icon: "♧",
  },
];

export default function DashboardShell({children}: {
  children: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-7">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-sm font-bold text-white">
            P
          </div>
          <div>
            <p className="text-lg font-bold tracking-tight">PayFlow</p>
            <p className="text-xs text-slate-400">Freelance payments</p>
          </div>
        </div>

        <div className="px-4 py-7">
          <p className="mb-3 px-3 text-[10px] font-bold uppercase tracking-[0.16em] text-slate-400">
            Workspace
          </p>

          <nav className="space-y-1">
            {navigation.map((item) => {
              const active =
                item.href === "/dashboard"
                  ? pathname === item.href
                  : pathname.startsWith(item.href);

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium transition ${
                    active
                      ? "bg-slate-950 text-white"
                      : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <span className="w-5 text-center text-base">
                    {item.icon}
                  </span>
                  {item.label}
                </Link>
              );
            })}
          </nav>
        </div>

        <div className="mt-auto p-4">
          <Link
            href="/dashboard/settings"
            className={`flex items-center gap-3 rounded-xl px-3 py-3 text-sm font-medium ${
              pathname.startsWith("/dashboard/settings")
                ? "bg-slate-950 text-white"
                : "text-slate-500 hover:bg-slate-100"
            }`}
          >
            <span className="w-5 text-center">⚙</span>
            Settings
          </Link>

          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3">
            <p className="text-xs font-semibold">PayFlow Testnet</p>
            <p className="mt-1 text-[11px] text-slate-500">
              Development environment
            </p>
          </div>
        </div>
      </aside>

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-20 items-center justify-between border-b border-slate-200 bg-white/90 px-5 backdrop-blur md:px-9">
          <div>
            <p className="text-sm font-semibold">Workspace</p>
            <p className="text-xs text-slate-400">
              Manage invoices and payments
            </p>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 sm:inline-flex">
              Testnet
            </span>

            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-600">
              PF
            </div>
          </div>
        </header>

        <nav className="flex gap-2 overflow-x-auto border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold ${
                pathname === item.href ||
                (item.href !== "/dashboard" && pathname.startsWith(item.href))
                  ? "bg-slate-950 text-white"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {item.label}
            </Link>
          ))}
          <Link
            href="/dashboard/settings"
            className="whitespace-nowrap rounded-lg bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-600"
          >
            Settings
          </Link>
        </nav>

        <main className="mx-auto w-full max-w-7xl p-5 md:p-9">
          {children}
        </main>
      </div>
    </div>
  );
}