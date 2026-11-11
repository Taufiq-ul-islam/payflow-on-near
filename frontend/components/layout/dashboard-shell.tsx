"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { getCurrentUser, logout } from "@/lib/auth";

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

export default function DashboardShell({
  children,
}: {
  children: ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();

  const [accountId, setAccountId] = useState("");
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [loggingOut, setLoggingOut] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;

    async function checkSession() {
      try {
        const user = await getCurrentUser();

        if (active) {
          setAccountId(user.account_id);
        }
      } catch {
        if (active) {
          router.replace("/login");
        }
      } finally {
        if (active) {
          setCheckingAuth(false);
        }
      }
    }

    checkSession();

    return () => {
      active = false;
    };
  }, [router]);

  async function handleLogout() {
    setLoggingOut(true);
    setError("");

    try {
      await logout();
      router.replace("/login");
      router.refresh();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Logout failed. Please try again."
      );
      setLoggingOut(false);
    }
  }

  if (checkingAuth || !accountId) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#f7f8fa]">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-4 border-slate-200 border-t-slate-900" />
          <p className="mt-4 text-sm text-slate-500">
            Verifying your session...
          </p>
        </div>
      </div>
    );
  }

  const shortAccountId =
    accountId.length > 24
      ? `${accountId.slice(0, 12)}...${accountId.slice(-8)}`
      : accountId;

  return (
    <div className="min-h-screen bg-[#f7f8fa] text-slate-900">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-slate-200 bg-white lg:flex">
        <div className="flex h-20 items-center gap-3 border-b border-slate-100 px-7">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-950 text-sm font-bold text-white">
            P
          </div>
          <div>
            <p className="text-lg font-bold tracking-tight">PayFlow</p>
            <p className="text-xs text-slate-400">
              Freelance payments
            </p>
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
        <header className="sticky top-0 z-20 flex min-h-20 items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-5 py-3 backdrop-blur md:px-9">
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

            <div
              className="hidden max-w-48 text-right sm:block"
              title={accountId}
            >
              <p className="text-xs font-semibold text-slate-700">
                Connected wallet
              </p>
              <p className="truncate text-[11px] text-slate-400">
                {shortAccountId}
              </p>
            </div>

            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-600">
              PF
            </div>

            <button
              onClick={handleLogout}
              disabled={loggingOut}
              className="rounded-lg border border-slate-200 px-3 py-2 text-xs font-semibold text-slate-600 transition hover:bg-slate-100 disabled:opacity-50"
            >
              {loggingOut ? "Signing out..." : "Logout"}
            </button>
          </div>
        </header>

        {error && (
          <div className="border-b border-red-200 bg-red-50 px-5 py-3 text-sm text-red-700 md:px-9">
            {error}
          </div>
        )}

        <nav className="flex gap-2 overflow-x-auto border-b border-slate-200 bg-white px-4 py-3 lg:hidden">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-semibold ${
                pathname === item.href ||
                (item.href !== "/dashboard" &&
                  pathname.startsWith(item.href))
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