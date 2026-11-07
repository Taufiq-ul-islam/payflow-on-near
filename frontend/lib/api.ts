const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api";

export async function apiRequest<T = any>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
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

export async function downloadCsv(endpoint: string, filename: string) {
  const response = await fetch(`${API_URL}${endpoint}`, {
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

export const DEMO_FREELANCER_ID =
  process.env.NEXT_PUBLIC_FREELANCER_ID || "YOUR_NEAR_ACCOUNT.testnet";