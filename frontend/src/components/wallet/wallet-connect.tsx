import { Button } from "@/components/ui/button";
import { useWallet } from "@/lib/solana/wallet-context";
import { explorerAddressUrl, SOL_SIMULATED_PRICE_USD } from "@/lib/solana/constants";

export function WalletConnect() {
  const {
    connected, connecting, publicKey, balance, verified, error,
    connect, connectPhantom, disconnect, refreshBalance, airdrop,
    network, reachable, note, mode,
  } = useWallet();

  if (!connected) {
    const local = network === "localnet";
    return (
      <div className="rounded-2xl border border-border bg-card p-6 text-center">
        <div className="mb-4 text-5xl">{local ? "🧪" : "🔗"}</div>
        <h3 className="font-display text-lg font-bold">
          {local ? "Local test wallet" : "Connect a Solana wallet"}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {local
            ? "Uses the FastAPI test keypair against solana-test-validator. No Phantom. Free test SOL with no public faucet limits."
            : "Phantom or Solflare on Devnet, or the server test wallet. Ownership is verified by signing. No private keys are stored in the browser."}
        </p>
        {note && <p className="mt-3 text-[11px] text-muted-foreground">{note}</p>}
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          <Button size="lg" onClick={connect} disabled={connecting}>
            {connecting ? "Connecting…" : local ? "Use local test wallet" : "Use server test wallet"}
          </Button>
          {!local && (
            <Button size="lg" variant="outline" onClick={connectPhantom} disabled={connecting}>
              Connect Phantom
            </Button>
          )}
        </div>
        <p className="mt-3 text-[10px] text-muted-foreground">
          {local
            ? reachable
              ? "Validator reachable at localhost:8899 · test SOL only, no real value"
              : "Start the validator: wsl -e bash -lc 'solana-test-validator'"
            : <>Free Devnet tokens only. Get SOL from{" "}
                <a href="https://faucet.solana.com/" target="_blank" rel="noopener noreferrer" className="text-primary underline">faucet.solana.com</a></>}
        </p>
      </div>
    );
  }

  const short = publicKey ? `${publicKey.slice(0, 6)}…${publicKey.slice(-4)}` : "";
  const usd = balance != null ? (balance * SOL_SIMULATED_PRICE_USD).toFixed(2) : "—";
  const href = explorerAddressUrl(publicKey!, network);

  return (
    <div className="rounded-2xl border border-primary/30 bg-gradient-to-r from-primary/5 to-transparent p-5">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex size-10 items-center justify-center rounded-full bg-primary/20 text-xl">
            {verified ? "✅" : "🔗"}
          </div>
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              Connected · {network} · {mode === "server" ? "server wallet" : "extension"}
            </p>
            {href ? (
              <a href={href} target="_blank" rel="noopener noreferrer" className="font-mono text-sm font-bold text-primary hover:underline">{short}</a>
            ) : (
              <p className="font-mono text-sm font-bold">{short}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <p className="font-display text-2xl font-extrabold">{balance?.toFixed(4) ?? "—"} SOL</p>
            <p className="text-xs text-muted-foreground">≈ ${usd} (simulated)</p>
          </div>
          <div className="flex gap-2">
            {network === "localnet" && (
              <Button variant="outline" size="sm" onClick={() => void airdrop(100)}>+100</Button>
            )}
            <Button variant="outline" size="sm" onClick={refreshBalance}>↻</Button>
            <Button variant="outline" size="sm" onClick={disconnect}>Disconnect</Button>
          </div>
        </div>
      </div>
      {network === "localnet" && (
        <p className="mt-3 text-[10px] text-muted-foreground">Local test blockchain — signatures will not appear on public Devnet Explorer.</p>
      )}
    </div>
  );
}
