/**
 * Wallet adapter: local test validator via FastAPI (no Phantom), or a browser
 * extension on public Devnet. No private keys are stored in the frontend.
 */
import "./polyfill";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { Connection, LAMPORTS_PER_SOL, PublicKey } from "@solana/web3.js";
import {
  airdropSol,
  backendCreateToken,
  backendHistory,
  backendSendSol,
  backendSplitBill,
  backendTransferToken,
  getSolanaStatus,
  type SolanaStatus,
} from "./backend";
import { DEVNET_URL, LOCALNET_URL, type SolanaNetwork } from "./constants";
import { sendSol as sendSolExtension, splitBill, validatePayment, getPaymentHistory, type PaymentRequest } from "./payments";
import { createToken as createTokenExtension, transferToken as transferTokenExtension, getForgedTokens, getTokenTransfers, type ForgedToken, type TokenTransfer } from "./coinforge";

interface PhantomProvider {
  isPhantom?: boolean;
  connect(): Promise<{ publicKey: PublicKey }>;
  disconnect(): Promise<void>;
  signMessage(message: Uint8Array, encoding: string): Promise<{ signature: Uint8Array }>;
  signTransaction(tx: any): Promise<any>;
  publicKey: PublicKey | null;
  isConnected: boolean;
  on(event: string, handler: (...args: any[]) => void): void;
  off(event: string, handler: (...args: any[]) => void): void;
}

function getProvider(): PhantomProvider | null {
  if (typeof window === "undefined") return null;
  const w = window as any;
  return w.phantom?.solana ?? w.solflare ?? w.solana ?? null;
}

export interface WalletState {
  mode: "server" | "extension";
  network: SolanaNetwork;
  reachable: boolean;
  note: string;
  connected: boolean;
  connecting: boolean;
  publicKey: string | null;
  balance: number | null;
  verified: boolean;
  error: string | null;
  connect(): Promise<void>;
  connectPhantom(): Promise<void>;
  disconnect(): Promise<void>;
  refreshBalance(): Promise<void>;
  airdrop(amount?: number): Promise<void>;
  sendPayment(recipient: string, amount: number, note?: string): Promise<PaymentRequest>;
  splitPayment(recipients: string[], total: number): Promise<PaymentRequest>;
  forgeToken(opts: { name: string; symbol: string; decimals: number; initialSupply: number }): Promise<ForgedToken>;
  sendToken(mint: string, to: string, amount: number, decimals: number): Promise<TokenTransfer>;
  getHistory(): Promise<{ payments: PaymentRequest[]; tokens: ForgedToken[]; transfers: TokenTransfer[] }>;
  provider: PhantomProvider | null;
  connection: Connection;
}

const WalletCtx = createContext<WalletState | null>(null);

function rpcFor(network: SolanaNetwork, rpcUrl?: string) {
  return rpcUrl || (network === "localnet" ? LOCALNET_URL : DEVNET_URL);
}

function paymentFromBackend(row: any): PaymentRequest {
  return {
    id: row.id ?? row.signature,
    sender: row.sender,
    recipient: row.recipient,
    amount: row.amount,
    token: "SOL",
    estimatedUsd: row.estimated_usd ?? row.estimatedUsd,
    status: row.status ?? "confirmed",
    signature: row.signature,
    timestamp: row.timestamp ?? Date.now(),
    note: row.note,
  };
}

export function WalletProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SolanaStatus | null>(null);
  const [provider, setProvider] = useState<PhantomProvider | null>(null);
  const [mode, setMode] = useState<"server" | "extension">("server");
  const [publicKey, setPublicKey] = useState<string | null>(null);
  const [balance, setBalance] = useState<number | null>(null);
  const [verified, setVerified] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const network: SolanaNetwork = status?.network ?? "localnet";
  const connection = useMemo(
    () => new Connection(rpcFor(network, status?.rpc_url), "confirmed"),
    [network, status?.rpc_url],
  );

  const loadStatus = useCallback(async () => {
    try {
      const next = await getSolanaStatus();
      setStatus(next);
      setError(null);
      return next;
    } catch (e: any) {
      setError(e?.message ?? "Wallet status unavailable");
      return null;
    }
  }, []);

  useEffect(() => {
    void loadStatus();
  }, [loadStatus]);

  const refreshBalance = useCallback(async () => {
    const next = await loadStatus();
    if (next && mode === "server") {
      setPublicKey(next.public_key);
      setBalance(next.balance_sol);
      return;
    }
    if (!publicKey) return;
    try {
      const lamports = await connection.getBalance(new PublicKey(publicKey));
      setBalance(lamports / LAMPORTS_PER_SOL);
    } catch {
      /* RPC may be down */
    }
  }, [connection, loadStatus, mode, publicKey]);

  const connect = useCallback(async () => {
    setConnecting(true);
    setError(null);
    try {
      const next = await loadStatus();
      if (!next) return;
      if (!next.reachable) {
        setError(next.network === "localnet"
          ? "Local validator is not running. Start it with solana-test-validator, then retry."
          : `Cannot reach ${next.rpc_url}`);
        return;
      }
      setMode("server");
      setPublicKey(next.public_key);
      setBalance(next.balance_sol);
      setVerified(true);
      if ((next.balance_sol ?? 0) <= 0 && next.network === "localnet") {
        const dropped = await airdropSol(100) as { balance_sol?: number };
        setBalance(dropped.balance_sol ?? next.balance_sol);
      }
    } catch (e: any) {
      setError(e?.message ?? "Local wallet connection failed");
    } finally {
      setConnecting(false);
    }
  }, [loadStatus]);

  const connectPhantom = useCallback(async () => {
    const p = getProvider();
    if (!p) { setError("No Solana wallet found. Install Phantom or Solflare, or use the local test wallet."); return; }
    setConnecting(true); setError(null);
    try {
      const resp = await p.connect();
      const pk = resp.publicKey.toBase58();
      setMode("extension");
      setPublicKey(pk); setProvider(p);
      const challenge = new TextEncoder().encode(`FinPilot ownership verification: ${pk} at ${Date.now()}`);
      const { signature } = await p.signMessage(challenge, "utf8");
      if (signature) setVerified(true); else setError("Signature verification failed");
      const lamports = await connection.getBalance(new PublicKey(pk));
      setBalance(lamports / LAMPORTS_PER_SOL);
    } catch (e: any) {
      setError(e?.message ?? "Wallet connection failed");
    } finally {
      setConnecting(false);
    }
  }, [connection]);

  const disconnect = useCallback(async () => {
    try { await provider?.disconnect(); } catch { /* ok */ }
    setPublicKey(null); setBalance(null); setVerified(false); setError(null); setMode("server");
  }, [provider]);

  const airdrop = useCallback(async (amount = 100) => {
    const dropped = await airdropSol(amount) as { balance_sol?: number };
    setBalance(dropped.balance_sol ?? null);
    await loadStatus();
  }, [loadStatus]);

  const sendPayment = useCallback(async (recipient: string, amount: number, note?: string) => {
    if (mode === "server") {
      const row = await backendSendSol(recipient, amount, note);
      await refreshBalance();
      return paymentFromBackend(row);
    }
    if (!provider || !publicKey) throw new Error("Wallet not connected");
    const payment = await sendSolExtension(connection, provider, new PublicKey(publicKey), recipient, amount, note);
    await refreshBalance();
    return payment;
  }, [connection, mode, provider, publicKey, refreshBalance]);

  const splitPayment = useCallback(async (recipients: string[], total: number) => {
    if (mode === "server") {
      const row = await backendSplitBill(recipients, total) as { payments?: any[]; total?: number };
      await refreshBalance();
      return paymentFromBackend({
        id: "split",
        sender: publicKey,
        recipient: `${recipients.length} recipients`,
        amount: total,
        estimated_usd: total * 25,
        status: "confirmed",
        timestamp: Date.now(),
        payments: row.payments,
      });
    }
    if (!provider || !publicKey) throw new Error("Wallet not connected");
    const entries = splitBill(total, recipients);
    for (const entry of entries) {
      const check = validatePayment(entry.amount, "SOL", balance ?? 0);
      if (!check.ok) throw new Error(check.error);
      await sendSolExtension(connection, provider, new PublicKey(publicKey), entry.recipient, entry.amount, `Split bill: ${entry.amount} SOL`);
    }
    await refreshBalance();
    return {
      id: "split",
      sender: publicKey,
      recipient: `${recipients.length} recipients`,
      amount: total,
      token: "SOL" as const,
      estimatedUsd: total * 25,
      status: "confirmed" as const,
      timestamp: Date.now(),
    };
  }, [balance, connection, mode, provider, publicKey, refreshBalance]);

  const forgeToken = useCallback(async (opts: { name: string; symbol: string; decimals: number; initialSupply: number }) => {
    if (mode === "server") {
      const row = await backendCreateToken({ name: opts.name, symbol: opts.symbol, decimals: opts.decimals, supply: opts.initialSupply }) as any;
      await refreshBalance();
      return {
        mintAddress: row.mint_address,
        name: row.name,
        symbol: row.symbol,
        decimals: row.decimals,
        supply: row.supply,
        createdAt: row.created_at,
        creator: row.creator,
      } satisfies ForgedToken;
    }
    if (!provider || !publicKey) throw new Error("Wallet not connected");
    const token = await createTokenExtension(connection, provider, new PublicKey(publicKey), opts);
    await refreshBalance();
    return token;
  }, [connection, mode, provider, publicKey, refreshBalance]);

  const sendToken = useCallback(async (mint: string, to: string, amount: number, decimals: number) => {
    if (mode === "server") {
      const row = await backendTransferToken({ mint, recipient: to, amount, decimals }) as any;
      await refreshBalance();
      return {
        id: row.id,
        mint: row.mint,
        from: row.from,
        to: row.to,
        amount: row.amount,
        signature: row.signature,
        timestamp: row.timestamp,
        status: row.status,
      } satisfies TokenTransfer;
    }
    if (!provider || !publicKey) throw new Error("Wallet not connected");
    const transfer = await transferTokenExtension(connection, provider, new PublicKey(publicKey), to, mint, amount, decimals);
    await refreshBalance();
    return transfer;
  }, [connection, mode, provider, publicKey, refreshBalance]);

  const getHistory = useCallback(async () => {
    if (mode === "extension") return { payments: getPaymentHistory(), tokens: getForgedTokens(), transfers: getTokenTransfers() };
    const data = await backendHistory();
    return {
      payments: data.payments.map(paymentFromBackend),
      tokens: data.tokens.map((row) => ({ mintAddress: row.mint_address, name: row.name, symbol: row.symbol,
        decimals: row.decimals, supply: row.supply, createdAt: row.created_at, creator: row.creator })),
      transfers: data.transfers as TokenTransfer[],
    };
  }, [mode]);

  useEffect(() => {
    if (!provider) return;
    const handleChange = () => { setPublicKey(null); setBalance(null); setVerified(false); };
    provider.on("accountChanged", handleChange);
    return () => { provider.off("accountChanged", handleChange); };
  }, [provider]);

  const value: WalletState = {
    mode,
    network,
    reachable: status?.reachable ?? false,
    note: status?.note ?? "",
    connected: !!publicKey && verified,
    connecting,
    publicKey,
    balance,
    verified,
    error,
    connect,
    connectPhantom,
    disconnect,
    refreshBalance,
    airdrop,
    sendPayment,
    splitPayment,
    forgeToken,
    sendToken,
    getHistory,
    provider,
    connection,
  };

  return <WalletCtx.Provider value={value}>{children}</WalletCtx.Provider>;
}

export function useWallet() {
  const ctx = useContext(WalletCtx);
  if (!ctx) throw new Error("useWallet must be inside WalletProvider");
  return ctx;
}

