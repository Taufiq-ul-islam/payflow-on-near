
"use client";

import { getNearConnector } from "@/lib/near-connect";

interface NearTransferWallet {
  signAndSendTransaction(params: {
    signerId: string;
    receiverId: string;
    actions: Array<{
      type: "FunctionCall";
      params: {
        methodName: string;
        args: object;
        gas: string;
        deposit: string;
      };
    }>;
  }): Promise<unknown>;
}

interface NearUsdcTransferParams {
  accountId: string;
  tokenContractId: string;
  receiverId: string;
  amount: string;
  registerReceiver?: boolean;
}

const STORAGE_REGISTRATION_DEPOSIT = "1250000000000000000000";

export async function sendNearUsdcTransfer({
  accountId,
  tokenContractId,
  receiverId,
  amount,
  registerReceiver = false,
}: NearUsdcTransferParams): Promise<unknown> {
  if (!accountId || !tokenContractId || !receiverId) {
    throw new Error("Missing NEAR transfer details.");
  }

  if (!/^[1-9]\d*$/.test(amount)) {
    throw new Error(
      "Transfer amount must be a positive integer in base units."
    );
  }

  const connector = getNearConnector();
  const wallet = (await connector.wallet()) as unknown as NearTransferWallet;

  const actions: NearTransferWallet["signAndSendTransaction"] extends (
    params: infer P
  ) => Promise<unknown>
    ? P extends { actions: infer A }
      ? A
      : never
    : never = [];

  if (registerReceiver) {
    actions.push({
      type: "FunctionCall",
      params: {
        methodName: "storage_deposit",
        args: {
          account_id: receiverId,
          registration_only: true,
        },
        gas: "30000000000000",
        deposit: STORAGE_REGISTRATION_DEPOSIT,
      },
    });
  }

  actions.push({
    type: "FunctionCall",
    params: {
      methodName: "ft_transfer",
      args: {
        receiver_id: receiverId,
        amount,
      },
      gas: "30000000000000",
      deposit: "1",
    },
  });

  return wallet.signAndSendTransaction({
    signerId: accountId,
    receiverId: tokenContractId,
    actions,
  });
}
