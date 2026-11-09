import { apiRequest } from "@/lib/api";

export interface AuthUser {
  authenticated: boolean;
  account_id: string;
}

export interface AuthChallenge {
  challenge_id: string;
  account_id: string;
  message: string;
  nonce: string;
  recipient: string;
  callback_url: string | null;
  expires_at: string;
}

export interface AuthVerifyResponse {
  authenticated: boolean;
  account_id: string;
  expires_at: string;
}

export async function getCurrentUser(): Promise<AuthUser> {
  return apiRequest<AuthUser>("/auth/me");
}

export async function logout(): Promise<void> {
  await apiRequest("/auth/logout", {
    method: "POST",
  });
}

export async function requestAuthChallenge(
  accountId: string
): Promise<AuthChallenge> {
  return apiRequest<AuthChallenge>("/auth/challenge", {
    method: "POST",
    body: JSON.stringify({
      account_id: accountId,
    }),
  });
}

export async function verifyWalletSignature(data: {
  challenge_id: string;
  account_id: string;
  public_key: string;
  signature: string;
}): Promise<AuthVerifyResponse> {
  return apiRequest<AuthVerifyResponse>("/auth/verify", {
    method: "POST",
    body: JSON.stringify(data),
  });
}