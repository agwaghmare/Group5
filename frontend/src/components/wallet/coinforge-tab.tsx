import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useWallet } from "@/lib/solana/wallet-context";
import { getForgedTokens, getTokenTransfers, type ForgedToken, type TokenTransfer } from "@/lib/solana/coinforge";
import { explorerTxUrl, explorerAddressUrl } from "@/lib/solana/constants";
import { WalletConnect } from "./wallet-connect";

export function CoinForgeTab() {
  const wallet = useWallet();
  const [tokens, setTokens] = useState(getForgedTokens);
  const [transfers, setTransfers] = useState(getTokenTransfers);

  useEffect(() => {
    if (!wallet.connected) return;
    let active = true;
    void wallet.getHistory().then((history) => {
      if (active) { setTokens(history.tokens); setTransfers(history.transfers); }
    }).catch((error: unknown) => {
      if (active) setCreateError(error instanceof Error ? error.message : "Could not load coins");
    });
    return () => { active = false; };
  }, [wallet.connected, wallet.getHistory]);

  // Create form
  const [name, setName] = useState("");
  const [symbol, setSymbol] = useState("");
  const [decimals, setDecimals] = useState("9");
  const [supply, setSupply] = useState("1000000");
  const [creating, setCreating] = useState(false);
  const [createResult, setCreateResult] = useState<ForgedToken | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);

  // Transfer form
  const [selectedMint, setSelectedMint] = useState("");
  const [transferTo, setTransferTo] = useState("");
  const [transferAmt, setTransferAmt] = useState("");
  const [transferring, setTransferring] = useState(false);
  const [transferResult, setTransferResult] = useState<TokenTransfer | null>(null);
  const [transferError, setTransferError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!wallet.connected || !wallet.publicKey) { setCreateError("Connect your test wallet first"); return; }
    if (!name.trim() || !symbol.trim()) { setCreateError("Name and symbol are required"); return; }
    if (!Number.isInteger(Number(decimals)) || Number(decimals) < 0 || Number(decimals) > 18) { setCreateError("Decimals must be 0–18"); return; }
    if (!Number.isFinite(Number(supply)) || Number(supply) <= 0) { setCreateError("Supply must be positive"); return; }

    setCreating(true); setCreateError(null); setCreateResult(null);
    try {
      const token = await wallet.forgeToken({
        name: name.trim(), symbol: symbol.trim().toUpperCase(), decimals: parseInt(decimals), initialSupply: parseFloat(supply),
      });
      setCreateResult(token);
      setTokens((previous) => [token, ...previous.filter((item) => item.mintAddress !== token.mintAddress)]);
      setSelectedMint(token.mintAddress);
    } catch (e: any) {
      setCreateError(e?.message ?? "Token creation failed");
    } finally { setCreating(false); }
  };

  const handleTransfer = async () => {
    if (!wallet.connected || !wallet.publicKey || !selectedMint || !transferTo || !transferAmt) return;
    if (!Number.isFinite(Number(transferAmt)) || Number(transferAmt) <= 0) { setTransferError("Enter a positive amount"); return; }
    const token = tokens.find((t) => t.mintAddress === selectedMint);
    if (!token) { setTransferError("Select a token"); return; }

    setTransferring(true); setTransferError(null); setTransferResult(null);
    try {
      const result = await wallet.sendToken(selectedMint, transferTo.trim(), Number(transferAmt), token.decimals);
      setTransferResult(result);
      setTransfers((previous) => [result, ...previous.filter((item) => item.id !== result.id)]);
    } catch (e: any) {
      setTransferError(e?.message ?? "Transfer failed");
    } finally { setTransferring(false); }
  };

  return (
    <div className="space-y-6">
      <WalletConnect />

      {wallet.connected && (
        <>
          {/* Create Token */}
          <div className="rounded-2xl border border-border bg-card p-5 space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-2xl">⚒️</span>
              <div>
                <h3 className="font-display text-sm font-bold uppercase tracking-[0.2em]">Create your currency</h3>
                <p className="text-[10px] text-muted-foreground">Create your own test currency, then send it to a Solana address below. Test coins have no real dollar value.</p>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Token Name</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  placeholder="FinPilot Coin" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Symbol</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  placeholder="FPC" maxLength={10} value={symbol} onChange={(e) => setSymbol(e.target.value)} />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Decimals</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  type="number" min="0" max="18" value={decimals} onChange={(e) => setDecimals(e.target.value)} />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Initial Supply</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  type="number" min="1" value={supply} onChange={(e) => setSupply(e.target.value)} />
              </div>
            </div>

            {createError && <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">❌ {createError}</div>}
            {createResult && (
              <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
                ✅ Created {createResult.symbol}! Mint:{" "}
                <a href={explorerAddressUrl(createResult.mintAddress, wallet.network) ?? undefined} target="_blank" rel="noopener noreferrer" className="font-mono underline">
                  {createResult.mintAddress.slice(0, 12)}…
                </a>
              </div>
            )}

            <Button className="w-full" onClick={handleCreate} disabled={creating || !name || !symbol}>
              {creating ? "Creating…" : "⚒️ Forge Token"}
            </Button>
          </div>

          {/* Your Tokens */}
          {tokens.length > 0 && (
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="mb-4 font-display text-sm font-bold uppercase tracking-[0.2em]">Your Forged Tokens</h3>
              <div className="space-y-2">
                {tokens.map((t) => (
                  <div key={t.mintAddress} className="flex items-center justify-between rounded-lg border border-border px-3 py-3">
                    <div>
                      <p className="font-display text-sm font-bold">{t.name} ({t.symbol})</p>
                      <p className="text-[10px] text-muted-foreground">
                        Supply: {t.supply.toLocaleString()} · Decimals: {t.decimals} · <a href={explorerAddressUrl(t.mintAddress, wallet.network) ?? undefined} target="_blank" rel="noopener noreferrer" className="text-primary underline">Mint ↗</a>
                      </p>
                    </div>
                    <span className="rounded-full bg-primary/20 px-2 py-0.5 text-[9px] font-bold text-primary">{wallet.network}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Transfer Token */}
          {tokens.length > 0 && (
            <div className="rounded-2xl border border-border bg-card p-5 space-y-4">
              <h3 className="font-display text-sm font-bold uppercase tracking-[0.2em]">Pay with your currency</h3>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Token</label>
                <select className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  value={selectedMint} onChange={(e) => setSelectedMint(e.target.value)}>
                  <option value="">Select token…</option>
                  {tokens.map((t) => <option key={t.mintAddress} value={t.mintAddress}>{t.symbol} — {t.name}</option>)}
                </select>
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Recipient address</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 font-mono text-sm"
                  placeholder="Recipient Solana public key" value={transferTo} onChange={(e) => setTransferTo(e.target.value)} />
              </div>
              <div>
                <label className="text-[10px] font-bold uppercase tracking-wider text-muted-foreground">Amount</label>
                <input className="mt-1 w-full rounded-lg border border-border bg-secondary/30 px-3 py-2 text-sm"
                  type="number" min="0" step="1" value={transferAmt} onChange={(e) => setTransferAmt(e.target.value)} />
              </div>

              {transferError && <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">❌ {transferError}</div>}
              {transferResult && (
                <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-xs text-primary">
                  ✅ Sent! <a href={explorerTxUrl(transferResult.signature, wallet.network) ?? undefined} target="_blank" rel="noopener noreferrer" className="underline">View on Explorer ↗</a>
                </div>
              )}

              <Button className="w-full" onClick={handleTransfer} disabled={transferring || !selectedMint || !transferTo || !transferAmt}>
                {transferring ? "Transferring…" : "Send Token"}
              </Button>
              <p className="text-[9px] text-muted-foreground text-center">Custom tokens have no real dollar value. Amounts are token-denominated.</p>
            </div>
          )}

          {/* Transfer History */}
          {transfers.length > 0 && (
            <div className="rounded-2xl border border-border bg-card p-5">
              <h3 className="mb-4 font-display text-sm font-bold uppercase tracking-[0.2em]">Token Transfer History</h3>
              <div className="space-y-2">
                {transfers.slice(0, 20).map((tx) => {
                  const token = tokens.find((t) => t.mintAddress === tx.mint);
                  return (
                    <div key={tx.id} className="flex items-center justify-between rounded-lg border border-border px-3 py-2 text-xs">
                      <div>
                        <p className="font-bold">{tx.amount} {token?.symbol ?? "?"} → {tx.to.slice(0, 10)}…</p>
                        <p className="text-muted-foreground">{new Date(tx.timestamp).toLocaleString()}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase ${tx.status === "confirmed" ? "bg-primary/20 text-primary" : "bg-destructive/20 text-destructive"}`}>{tx.status}</span>
                        <a href={explorerTxUrl(tx.signature, wallet.network) ?? undefined} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">↗</a>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
