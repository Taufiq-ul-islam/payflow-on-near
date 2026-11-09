"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { getNearConnector } from "@/lib/near-connect";
import {
  requestAuthChallenge,
  verifyWalletSignature,
} from "@/lib/auth";

interface NearAccount {
  accountId: string;
}

interface NearSignInEvent {
  accounts: NearAccount[];
}

interface SignedMessage {
  publicKey?: string;
  signature?: string;
  public_key?: string;
}

interface SignMessageWallet {
  signMessage(params: {
    message: string;
    recipient: string;
    nonce: Uint8Array;
    callbackUrl?: string;
  }): Promise<SignedMessage>;
}

function decodeBase64(value: string): Uint8Array {
  const binary = window.atob(value);
  const bytes = new Uint8Array(binary.length);

  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }

  return bytes;
}

export default function LoginPage() {
  const router = useRouter();

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleLogin() {
    setLoading(true);
    setError("");

    try {
      const connector = getNearConnector();

      // Step 1: Connect the wallet and obtain its account ID.
      const account = await new Promise<NearAccount>(
        async (resolve, reject) => {
          let settled = false;

          connector.on("wallet:signIn", (event: NearSignInEvent) => {
            if (settled) return;

            const selectedAccount = event.accounts?.[0];

            if (!selectedAccount?.accountId) {
              settled = true;
              reject(new Error("No NEAR account was returned by the wallet."));
              return;
            }

            settled = true;
            resolve(selectedAccount);
          });

          try {
            await connector.connect();
          } catch (err) {
            if (!settled) {
              settled = true;
              reject(err);
            }
          }
        }
      );

      // Step 2: Request a challenge specifically for this account.
      const challenge = await requestAuthChallenge(account.accountId);

      // Step 3: Ask the connected wallet to sign the backend challenge.
      const wallet = (await connector.wallet()) as unknown as SignMessageWallet;

      const signedMessage = await wallet.signMessage({
        message: challenge.message,
        recipient: challenge.recipient,
        nonce: decodeBase64(challenge.nonce),
        ...(challenge.callback_url
          ? { callbackUrl: challenge.callback_url }
          : {}),
      });

      const publicKey =
        signedMessage.publicKey ?? signedMessage.public_key;

      if (!publicKey || !signedMessage.signature) {
        throw new Error(
          "The wallet did not return a valid signed message."
        );
      }

      // Step 4: Backend verifies the signature and creates the session.
      await verifyWalletSignature({
        challenge_id: challenge.challenge_id,
        account_id: account.accountId,
        public_key: publicKey,
        signature: signedMessage.signature,
      });

      // The backend sets the HttpOnly session cookie.
      router.replace("/dashboard");
    } catch (err) {
      console.error("Wallet login failed:", err);

      setError(
        err instanceof Error
          ? err.message
          : "Wallet login failed. Please try again."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-950 px-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-800 bg-slate-900 p-8 shadow-xl">
        <div className="mb-8 text-center">
          <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 text-xl font-bold text-white">
            P
          </div>

          <h1 className="text-2xl font-bold text-white">
            Welcome to PayFlow
          </h1>

          <p className="mt-2 text-sm text-slate-400">
            Connect your NEAR wallet to access your freelancer dashboard.
          </p>
        </div>

        {error && (
          <div className="mb-5 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          onClick={handleLogin}
          disabled={loading}
          className="w-full rounded-xl bg-blue-600 px-5 py-3 font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Connecting..." : "Connect NEAR Wallet"}
        </button>

        <p className="mt-5 text-center text-xs text-slate-500">
          You will be asked to sign an authentication message.
          This does not initiate a transaction or spend funds.
        </p>

        <div className="mt-6 border-t border-slate-800 pt-5 text-center">
          <span className="text-xs text-slate-500">
            PayFlow · NEAR Testnet
          </span>
        </div>
      </div>
    </main>
  );
}