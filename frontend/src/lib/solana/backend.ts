import { readCustomerSession } from "@/lib/customer-session";
import type { SolanaNetwork } from "./constants";

const BASE = (import.meta.env["VITE_PNC_API_URL"] as string | undefined) ?? "";

export interface SolanaStatus {
  network: SolanaNetwork;
  rpc_url: string;
  reachable: boolean;
  signing: "server";
  phantom_required: boolean;
  public_key: string;
  balance_sol: number | null;
  estimated_usd: number | null;
  note: string;
  limits: {
    per_request_usd: number;
    daily_usd: number;
    daily_spent_usd: number;
    sol_simulated_price_usd: number;
  };
}

function authHeaders(): HeadersInit {
  const session = readCustomerSession();
  if (!session?.token) throw new Error("Sign in to use the Wallet.");
  return { Accept: "application/json", "Content-Type": "application/json", Authorization: `Bearer ${session.token}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: { ...authHeaders(), ...(init?.headers ?? {}) } });
  const payload = (await response.json().catch(() => ({}))) as T & { detail?: string | { msg?: string } };
  if (!response.ok) {
    const detail = payload.detail;
    const message = typeof detail === "string" ? detail : detail && typeof detail === "object" && "msg" in detail ? String(detail.msg) : `Solana request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

export function getSolanaStatus() {
  return request<SolanaStatus>("/api/v1/solana/status");
}

export function airdropSol(amount = 100) {
  return request("/api/v1/solana/airdrop", { method: "POST", body: JSON.stringify({ amount }) });
}

export function backendSendSol(recipient: string, amount: number, note?: string) {
  return request("/api/v1/solana/send", { method: "POST", body: JSON.stringify({ recipient, amount, note }) });
}

export function backendSplitBill(recipients: string[], amount: number) {
  return request("/api/v1/solana/split", { method: "POST", body: JSON.stringify({ recipients, amount }) });
}

export function backendCreateToken(body: { name: string; symbol: string; decimals: number; supply: number }) {
  return request("/api/v1/solana/tokens", { method: "POST", body: JSON.stringify(body) });
}

export function backendTransferToken(body: { mint: string; recipient: string; amount: number; decimals: number }) {
  return request("/api/v1/solana/tokens/transfer", { method: "POST", body: JSON.stringify(body) });
}

export function backendHistory() {
  return request<{ payments: any[]; tokens: any[]; transfers: any[]; network: SolanaNetwork }>("/api/v1/solana/history");
}
