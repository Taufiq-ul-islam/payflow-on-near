export function formatCurrency(
  amount: string | number,
  currency = "USD"
) {
  const value = Number(amount || 0);

  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number.isFinite(value) ? value : 0);
}

export function formatDate(value?: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

export function formatDateTime(value?: string | null) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function shortAddress(value?: string | null) {
  if (!value) return "—";
  if (value.length < 18) return value;

  return `${value.slice(0, 9)}...${value.slice(-6)}`;
}

export function statusLabel(status?: string) {
  if (!status) return "Unknown";

  return status
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * Convert an integer amount in token base units into a readable decimal.
 * Uses BigInt exclusively; never converts token amounts to Number.
 */
export function formatTokenAmount(
  rawAmount: string | bigint,
  decimals: number,
  maxFractionDigits = 8
): string {
  if (!Number.isInteger(decimals) || decimals < 0) {
    throw new Error("Invalid token decimals");
  }

  if (!Number.isInteger(maxFractionDigits) || maxFractionDigits < 0) {
    throw new Error("Invalid maximum fraction digits");
  }

  const amount = BigInt(rawAmount);
  const negative = amount < 0n;
  const absolute = negative ? -amount : amount;

  const divisor = 10n ** BigInt(decimals);
  const integerPart = absolute / divisor;
  const remainder = absolute % divisor;

  const precision = Math.min(decimals, maxFractionDigits);
  const roundingFactor = 10n ** BigInt(precision);

  // Round using integer arithmetic.
  const roundedFraction =
    (remainder * roundingFactor + divisor / 2n) / divisor;

  let whole = integerPart;
  let fraction = roundedFraction;

  // Handle rounding that carries into the integer part.
  if (fraction >= roundingFactor && precision > 0) {
    whole += 1n;
    fraction -= roundingFactor;
  }

  const formattedWhole = whole
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ",");

  if (precision === 0) {
    return `${negative ? "-" : ""}${formattedWhole}`;
  }

  const formattedFraction = fraction
    .toString()
    .padStart(precision, "0")
    .replace(/0+$/, "");

  return (
    `${negative ? "-" : ""}${formattedWhole}` +
    (formattedFraction ? `.${formattedFraction}` : "")
  );
}