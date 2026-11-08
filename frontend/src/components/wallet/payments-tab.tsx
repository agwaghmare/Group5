import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { useWallet } from "@/lib/solana/wallet-context";
import {
  validatePayment,
  splitBill,
  getPaymentHistory,
  solToUsd,
  type PaymentRequest,
} from "@/lib/solana/payments";
import {
  explorerTxUrl,
  SOL_SIMULATED_PRICE_USD,
  PAYMENT_REQUEST_LIMIT_USD,
  DAILY_PAYMENT_LIMIT_USD,
} from "@/lib/solana/constants";
import { WalletConnect } from "./wallet-connect";

export function PaymentsTab() {
  const wallet = useWallet();
  const [recipient, setRecipient] = useState("");
  const [amount, setAmount] = useState("");
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState<PaymentRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [mode, setMode] = useState<"send" | "split">("send");
  const [splitAddrs, setSplitAddrs] = useState("");
  const [history, setHistory] = useState<PaymentRequest[]>(() => getPaymentHistory());

  useEffect(() => {
    if (!wallet.connected) return;
    let active = true;
    void wallet.getHistory().then((data) => { if (active) setHistory(data.payments); })
      .catch((error: unknown) => { if (active) setError(error instanceof Error ? error.message : "Could not load payments"); });
    return () => { active = false; };
  }, [wallet.connected, wallet.getHistory]);

  const handleSend = async () => {
    if (!wallet.connected || !wallet.publicKey) return;
    const amt = parseFloat(amount);
    const v = validatePayment(amt, "SOL", wallet.balance ?? 0);
    setWarnings(v.warnings);
    if (!v.ok) {
      setError(v.error ?? "Invalid payment");
      return;
    }
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const p = await wallet.sendPayment(recipient.trim(), amt, note || undefined);
      setResult(p);
      setHistory((await wallet.getHistory()).payments);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Transaction failed");
    } finally {
      setSending(false);
    }
  };

  const handleSplit = async () => {
    if (!wallet.connected || !wallet.publicKey) return;
    const total = parseFloat(amount);
    const addrs = splitAddrs.split(/[\n,]+/).map((s) => s.trim()).filter(Boolean);
    if (addrs.length < 2) {
      setError("Enter at least 2 addresses to split between");
      return;
    }
    const entries = splitBill(total, addrs);
    for (const entry of entries) {
      const v = validatePayment(entry.amount, "SOL", wallet.balance ?? 0);
      if (!v.ok) {
        setError(`Split to ${entry.recipient.slice(0, 8)}…: ${v.error}`);
        return;
      }
    }
    setSending(true);
    setError(null);
    setResult(null);
    try {
      const p = await wallet.splitPayment(addrs, total);
      setResult(p);
      setHistory((await wallet.getHistory()).payments);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Split transaction failed");
    } finally {
      setSending(false);
    }
  };

  const usdEq = parseFloat(amount) > 0 ? solToUsd(parseFloat(amount)).toFixed(2) : "0.00";

  return (
    <div className="space-y-6">
      <WalletConnect />

      {wallet.connected && (
        <>
          <div className="flex gap-2">
            <Button variant={mode === "send" ? "default" : "outline"} onClick={() => setMode("send")}>
              💸 Send
            </Button>
            <Button variant={mode === "split" ? "default" : "outline"} onClick={() => setMode("split")}>
              🧾 Split Bill
            </Button>
          </div>

          <div className="space-y-4 rounded-2xl border border-border bg-card p-5">
            <h3 className="font-display text-sm font-bold uppercase tracking-[0.2em]">
              {mode === "send" ? "Send test SOL" : "Split Bill"}
            </h3>

            {mode === "send" ? (
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Recipient address
                </label>
                <input
                  className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 font-mono text-sm"
                  placeholder="Solana public key"
                  value={recipient}
                  onChange={(e) => setRecipient(e.target.value)}
                />
              </div>
            ) : (
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                  Addresses (one per line or comma-separated)
                </label>
                <textarea
                  className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 font-mono text-sm"
                  rows={3}
                  placeholder={"Address1\nAddress2\nAddress3"}
                  value={splitAddrs}
                  onChange={(e) => setSplitAddrs(e.target.value)}
                />
              </div>
            )}

            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                {mode === "split" ? "Total amount (SOL)" : "Amount (SOL)"}
              </label>
              <div className="flex items-center gap-2">
                <input
                  className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  type="number"
                  step="0.001"
                  min="0"
                  placeholder="0.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
                <span className="shrink-0 text-xs text-muted-foreground">≈ ${usdEq}</span>
              </div>
              <div className="mt-2">
                <div className="flex justify-between text-[9px] text-muted-foreground">
                  <span>$0</span>
                  <span>${PAYMENT_REQUEST_LIMIT_USD} limit</span>
                </div>
                <Progress value={Math.min(100, (parseFloat(usdEq) / PAYMENT_REQUEST_LIMIT_USD) * 100)} className="h-1.5" />
              </div>
            </div>

            <div>
              <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">
                Note (optional)
              </label>
              <input
                className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                placeholder="What's this for?"
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>

            {warnings.map((w, i) => (
              <div key={i} className="rounded-lg border border-yellow-500/30 bg-yellow-500/10 px-3 py-2 text-xs text-yellow-400">
                ⚠️ {w}
              </div>
            ))}
            {error && (
              <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
                ❌ {error}
              </div>
            )}
            {result && (
              <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
                ✅ {result.status === "confirmed" ? "Confirmed" : result.status}! {result.amount} SOL →{" "}
                {result.recipient.slice(0, 12)}…
                {result.signature && explorerTxUrl(result.signature, wallet.network) && (
                  <a
                    href={explorerTxUrl(result.signature, wallet.network)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 underline"
                  >
                    View on Explorer ↗
                  </a>
                )}
              </div>
            )}

            <Button
              className="w-full"
              disabled={sending || !amount || (mode === "send" && !recipient)}
              onClick={() => void (mode === "send" ? handleSend() : handleSplit())}
            >
              {sending ? "Sending…" : mode === "send" ? `Send ${amount || "0"} SOL` : `Split ${amount || "0"} SOL`}
            </Button>

            <p className="text-center text-[9px] text-muted-foreground">
              Devnet/localnet only · ${PAYMENT_REQUEST_LIMIT_USD}/tx limit · ${DAILY_PAYMENT_LIMIT_USD}/day · SOL
              simulated at ${SOL_SIMULATED_PRICE_USD}
            </p>
          </div>

          {history.length > 0 && (
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="mb-4 font-display text-sm font-bold uppercase tracking-[0.2em]">Transaction History</h3>
              <div className="space-y-2">
                {history.slice(0, 20).map((tx) => (
                  <div key={tx.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-xs">
                    <div className="min-w-0 flex-1">
                      <p className="font-mono font-bold">
                        {tx.amount} SOL → {tx.recipient.slice(0, 10)}…
                      </p>
                      <p className="text-muted-foreground">
                        {new Date(tx.timestamp).toLocaleString()} · ≈${tx.estimatedUsd.toFixed(2)}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${
                          tx.status === "confirmed" ? "bg-primary/20 text-primary" : "bg-destructive/20 text-destructive"
                        }`}
                      >
                        {tx.status}
                      </span>
                      {tx.signature && explorerTxUrl(tx.signature, wallet.network) && (
                        <a
                          href={explorerTxUrl(tx.signature, wallet.network)!}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary hover:underline"
                        >
                          ↗
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
