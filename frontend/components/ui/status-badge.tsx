import { statusLabel } from "@/lib/format";

export default function StatusBadge({
  status,
}: {
  status?: string;
}) {
  const normalized = (status || "").toUpperCase();

  let styles =
    "border-slate-200 bg-slate-50 text-slate-600";

  if (["PAID", "SUCCESS"].includes(normalized)) {
    styles = "border-emerald-200 bg-emerald-50 text-emerald-700";
  } else if (
    ["PENDING", "PENDING_DEPOSIT", "PROCESSING", "KNOWN_DEPOSIT_TX"].includes(
      normalized
    )
  ) {
    styles = "border-amber-200 bg-amber-50 text-amber-700";
  } else if (
    ["FAILED", "REFUNDED", "CANCELLED", "EXPIRED"].includes(normalized)
  ) {
    styles = "border-rose-200 bg-rose-50 text-rose-700";
  }

  return (
    <span
      className={`inline-flex whitespace-nowrap rounded-full border px-2.5 py-1 text-[11px] font-semibold ${styles}`}
    >
      {statusLabel(status)}
    </span>
  );
}