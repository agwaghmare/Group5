export const LOCALNET_URL = "http://127.0.0.1:8899";
export const DEVNET_URL = "https://api.devnet.solana.com";
export const PAYMENT_REQUEST_LIMIT_USD = 200;
export const DAILY_PAYMENT_LIMIT_USD = 500;
export const SOL_SIMULATED_PRICE_USD = 25;
export const DEVNET_EXPLORER = "https://explorer.solana.com";

export type SolanaNetwork = "localnet" | "devnet" | "testnet";

export function rpcUrlFor(network: SolanaNetwork): string {
  if (network === "localnet") return LOCALNET_URL;
  if (network === "testnet") return "https://api.testnet.solana.com";
  return DEVNET_URL;
}

export function explorerTxUrl(sig: string, network: SolanaNetwork = "devnet") {
  if (network === "localnet") return null;
  return `${DEVNET_EXPLORER}/tx/${sig}?cluster=${network}`;
}

export function explorerAddressUrl(addr: string, network: SolanaNetwork = "devnet") {
  if (network === "localnet") return null;
  return `${DEVNET_EXPLORER}/address/${addr}?cluster=${network}`;
}

export const SUPPORTED_SPL_TOKENS: { mint: string; symbol: string; name: string; decimals: number; simulatedPriceUsd: number }[] = [
  { mint: "So11111111111111111111111111111111111111112", symbol: "wSOL", name: "Wrapped SOL", decimals: 9, simulatedPriceUsd: SOL_SIMULATED_PRICE_USD },
];
