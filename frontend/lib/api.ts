const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    credentials: "include",
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;

    try {
      const error = await response.json();
      message = error.detail || error.message || message;
    } catch {
      // Keep the HTTP fallback message.
    }

    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}


export async function downloadCsv(
  endpoint: string,
  filename: string
) {
  const response = await fetch(`${API_URL}${endpoint}`, {
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`CSV export failed (${response.status})`);
  }

  const blob = await response.blob();
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;

  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  URL.revokeObjectURL(url);
}

import type { Refund } from "@/lib/types";

export async function getRefunds(): Promise<Refund[]> {
  const result = await apiRequest<Refund[]>("/refunds");

  return Array.isArray(result)
    ? result.map((refund) => ({
        ...refund,
        id: refund.id || refund.refund_id || "",
      }))
    : [];
}

export async function getRefund(refundId: string): Promise<Refund> {
  const result = await apiRequest<Refund>(`/refunds/${refundId}`);

  return {
    ...result,
    id: result.id || result.refund_id || refundId,
  };
}

export interface RefundQuotePayload {
  destination_network: string;
  destination_asset: string;
  destination_address: string;
  requested_amount: string;
}

export interface RefundDepositPayload {
  tx_hash: string;
  near_sender_account: string;
}

export async function createRefundQuote(
  paymentAttemptId: string,
  idempotencyKey?: string
): Promise<Refund> {
  const result = await apiRequest<Refund>(
    `/refunds/quote/${paymentAttemptId}`,
    {
      method: "POST",
      headers: idempotencyKey
        ? { "Idempotency-Key": idempotencyKey }
        : undefined,
    }
  );

  return {
    ...result,
    id: result.id || result.refund_id || "",
  };
}

export async function approveRefund(refundId: string): Promise<Refund> {
  const result = await apiRequest<Refund>(
    `/refunds/${refundId}/approve`,
    { method: "POST" }
  );

  return {
    ...result,
    id: result.id || result.refund_id || refundId,
  };
}

export async function submitRefundDeposit(
  refundId: string,
  payload: RefundDepositPayload
): Promise<Refund> {
  const result = await apiRequest<Refund>(
    `/refunds/${refundId}/deposit-submit`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    }
  );

  return {
    ...result,
    id: result.id || result.refund_id || refundId,
  };
}

export async function reconcileRefund(
  refundId: string
): Promise<Refund> {
  const result = await apiRequest<Refund>(
    `/refunds/${refundId}/reconcile`,
    { method: "POST" }
  );

  return {
    ...result,
    id: result.id || result.refund_id || refundId,
  };
}