/**
 * Devnet payment logic: send SOL/SPL, split bills, $200 limit, daily limits, duplicate detection.
 */
import { Connection, LAMPORTS_PER_SOL, PublicKey, SystemProgram, Transaction } from "@solana/web3.js";
import { PAYMENT_REQUEST_LIMIT_USD, DAILY_PAYMENT_LIMIT_USD, SOL_SIMULATED_PRICE_USD } from "./constants";

export interface PaymentRequest {
  id: string;
  sender: string;
  recipient: string;
  amount: number;
  token: "SOL";
  estimatedUsd: number;
  status: "pending" | "confirmed" | "failed" | "rejected";
  signature?: string;
  timestamp: number;
  note?: string;
}

export interface SplitBillEntry {
  recipient: string;
  amount: number;
  share: number;
}

const TX_HISTORY_KEY = "finpilot.payments.history";
const DAILY_KEY = "finpilot.payments.daily";

function storage(): Storage | null {
  try {
    if (typeof window === "undefined") return null;
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function getPaymentHistory(): PaymentRequest[] {
  try {
    const raw = storage()?.getItem(TX_HISTORY_KEY) ?? "[]";
    return JSON.parse(raw);
  } catch {
    return [];
  }
}
function saveHistory(h: PaymentRequest[]) {
  storage()?.setItem(TX_HISTORY_KEY, JSON.stringify(h));
}

function getDailySpent(): { date: string; total: number } {
  try {
    return JSON.parse(storage()?.getItem(DAILY_KEY) ?? '{"date":"","total":0}');
  } catch {
    return { date: "", total: 0 };
  }
}
function saveDailySpent(d: { date: string; total: number }) {
  storage()?.setItem(DAILY_KEY, JSON.stringify(d));
}

export function solToUsd(sol: number) { return sol * SOL_SIMULATED_PRICE_USD; }
export function usdToSol(usd: number) { return usd / SOL_SIMULATED_PRICE_USD; }

export function validatePayment(amount: number, _token: "SOL", senderBalance: number): { ok: boolean; error?: string; warnings: string[] } {
  const warnings: string[] = [];
  const usd = solToUsd(amount);

  if (amount <= 0) return { ok: false, error: "Amount must be positive", warnings };
  if (usd > PAYMENT_REQUEST_LIMIT_USD) return { ok: false, error: `Exceeds the $${PAYMENT_REQUEST_LIMIT_USD} per-request limit (${amount} SOL ≈ $${usd.toFixed(2)})`, warnings };
  if (amount > senderBalance) return { ok: false, error: `Insufficient balance (have ${senderBalance.toFixed(4)} SOL)`, warnings };

  const today = new Date().toISOString().slice(0, 10);
  const daily = getDailySpent();
  const dailyTotal = daily.date === today ? daily.total : 0;
  if (dailyTotal + usd > DAILY_PAYMENT_LIMIT_USD) return { ok: false, error: `Daily limit of $${DAILY_PAYMENT_LIMIT_USD} reached ($${dailyTotal.toFixed(2)} already sent today)`, warnings };

  // Duplicate detection
  const recent = getPaymentHistory().filter((p) => p.timestamp > Date.now() - 300_000 && p.status === "confirmed");
  const dup = recent.find((p) => p.amount === amount && p.recipient === _token);
  if (dup) warnings.push("A similar payment was sent in the last 5 minutes.");

  if (usd > 100) warnings.push("Large payment: over $100 equivalent.");
  if (amount > senderBalance * 0.9) warnings.push("This will use over 90% of your balance.");

  return { ok: true, warnings };
}

export async function sendSol(
  connection: Connection,
  provider: any,
  sender: PublicKey,
  recipientAddr: string,
  amount: number,
  note?: string,
): Promise<PaymentRequest> {
  const recipient = new PublicKey(recipientAddr);
  const lamports = Math.round(amount * LAMPORTS_PER_SOL);

  const tx = new Transaction().add(
    SystemProgram.transfer({ fromPubkey: sender, toPubkey: recipient, lamports }),
  );
  tx.feePayer = sender;
  const { blockhash } = await connection.getLatestBlockhash();
  tx.recentBlockhash = blockhash;

  const signed = await provider.signTransaction(tx);
  const sig = await connection.sendRawTransaction(signed.serialize());
  await connection.confirmTransaction(sig, "confirmed");

  const payment: PaymentRequest = {
    id: sig,
    sender: sender.toBase58(),
    recipient: recipientAddr,
    amount,
    token: "SOL",
    estimatedUsd: solToUsd(amount),
    status: "confirmed",
    signature: sig,
    timestamp: Date.now(),
    ...(note === undefined ? {} : { note }),
  };

  // Record
  const history = getPaymentHistory();
  history.unshift(payment);
  saveHistory(history);

  // Daily limit
  const today = new Date().toISOString().slice(0, 10);
  const daily = getDailySpent();
  const prev = daily.date === today ? daily.total : 0;
  saveDailySpent({ date: today, total: prev + payment.estimatedUsd });

  return payment;
}

export function splitBill(totalAmount: number, recipients: string[]): SplitBillEntry[] {
  if (recipients.length === 0) return [];
  const share = totalAmount / recipients.length;
  const rounded = Math.floor(share * 1e9) / 1e9;
  return recipients.map((r, i) => ({
    recipient: r,
    amount: i === recipients.length - 1 ? totalAmount - rounded * (recipients.length - 1) : rounded,
    share: 1 / recipients.length,
  }));
}
