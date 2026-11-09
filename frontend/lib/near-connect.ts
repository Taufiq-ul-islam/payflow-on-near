"use client";

import { NearConnector } from "@hot-labs/near-connect";

let connector: NearConnector | null = null;

export function getNearConnector(): NearConnector {
  if (!connector) {
    connector = new NearConnector({
      network: "testnet",
      features: {
        signMessage: true,
        testnet: true,
      },
    });
  }

  return connector;
}