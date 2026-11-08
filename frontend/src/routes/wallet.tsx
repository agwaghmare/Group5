import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { Component, useState, lazy, Suspense, type ErrorInfo, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FinpilotHeader } from "@/components/finpilot-header";
import { RequireCustomer } from "@/components/require-customer";
import { MilestoneTracker } from "@/components/finance/milestone-tracker";
import { useCustomerSession } from "@/lib/customer-session";
import { loadTracker } from "@/lib/finance-api";

// Lazy-load Solana-dependent components so they are never bundled into the
// Nitro/Cloudflare Workers server build (rpc-websockets and @solana/codecs
// have no "workerd" exports condition).
const LazyPaymentsTab = lazy(() =>
  import("@/components/wallet/payments-tab").then((m) => ({ default: m.PaymentsTab })),
);
const LazyCoinForgeTab = lazy(() =>
  import("@/components/wallet/coinforge-tab").then((m) => ({ default: m.CoinForgeTab })),
);
const LazyWalletProvider = lazy(() =>
  import("@/lib/solana/wallet-context").then((m) => ({ default: m.WalletProvider })),
);

type WalletView = "milestones" | "payments" | "coinforge";

export const Route = createFileRoute("/wallet")({
  head: () => ({
    meta: [
      { title: "Wallet — FINPILOT" },
      { name: "description", content: "Milestone tracker, Solana Devnet payments, CoinForge, rewards wallet." },
      { property: "og:title", content: "Wallet — FINPILOT" },
      { property: "og:description", content: "Milestone tracker, Solana Devnet payments, CoinForge, rewards wallet." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: WalletPage,
});

const TABS: { id: WalletView; label: string; icon: string }[] = [
  { id: "milestones", label: "Milestones", icon: "🏆" },
  { id: "payments", label: "Payments", icon: "💸" },
  { id: "coinforge", label: "CoinForge", icon: "⚒️" },
];

class SolanaErrorBoundary extends Component<
  { children: ReactNode; label: string },
  { error: Error | null }
> {
  override state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Solana wallet tab failed", error, info);
  }

  override render() {
    if (this.state.error) {
      return (
        <div className="space-y-3 rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-5 text-sm">
          <div className="flex items-start gap-3">
            <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
            <div>
              <p className="font-medium text-destructive">{this.props.label} could not load</p>
              <p className="mt-1 text-muted-foreground">
                {this.state.error.message || "The Solana client failed to start in this browser session."}
              </p>
            </div>
          </div>
          <Button variant="outline" size="sm" onClick={() => this.setState({ error: null })}>
            Try again
          </Button>
        </div>
      );
    }
    return this.props.children;
  }
}

function SolanaPanel({ children }: { children: ReactNode }) {
  return (
    <SolanaErrorBoundary label="This Solana tab">
      <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl bg-secondary/50" />}>
        <LazyWalletProvider>
          <Suspense fallback={<div className="h-40 animate-pulse rounded-2xl bg-secondary/50" />}>{children}</Suspense>
        </LazyWalletProvider>
      </Suspense>
    </SolanaErrorBoundary>
  );
}

function WalletPage() {
  const session = useCustomerSession();
  const [view, setView] = useState<WalletView>("milestones");
  const tracker = useQuery({
    queryKey: ["finance", "tracker", session?.email, session?.token],
    queryFn: loadTracker,
    enabled: Boolean(session?.token) && !session?.isStaff,
    retry: false,
  });
  const latest = tracker.data?.snapshots.at(-1);
  const history = tracker.data?.snapshots ?? [];

  return (
    <RequireCustomer>
      <div className="flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
        <FinpilotHeader miniWheel />
        <main className="fifth-page-enter flex min-h-0 flex-1 flex-col overflow-y-auto rounded-[2rem] border border-border px-6 py-8 md:px-12 lg:px-16">
          <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
            <p className="font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">02 — Wallet</p>
          </div>
          <h1 className="font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
            {view === "milestones" && "Milestone Tracker 🏆"}
            {view === "payments" && "Test Payments 💸"}
            {view === "coinforge" && "CoinForge ⚒️"}
          </h1>
          <p className="mt-3 max-w-xl text-muted-foreground">
            {view === "milestones" &&
              "Level up your financial life. Complete milestones, earn XP and FinPilot Credits, and unlock rewards."}
            {view === "payments" &&
              "Send test SOL or split a bill. To create and pay with your own test currency, open CoinForge."}
            {view === "coinforge" &&
              "Create your own test currency and pay another Solana address. Your coins and transfer history are saved locally."}
          </p>

          <div className="mt-6 flex flex-wrap gap-2">
            {TABS.map((tab) => (
              <Button
                key={tab.id}
                variant={view === tab.id ? "default" : "outline"}
                onClick={() => setView(tab.id)}
                className="gap-1.5"
              >
                <span>{tab.icon}</span> {tab.label}
              </Button>
            ))}
          </div>

          <div className="mt-8 min-h-0 flex-1">
            {session?.isStaff && <p className="text-sm text-muted-foreground">Sign in with a customer email.</p>}

            {view === "milestones" && (
              <>
                {!session?.isStaff && tracker.isLoading && (
                  <div className="h-40 animate-pulse rounded-2xl bg-secondary/50" />
                )}
                {!session?.isStaff && tracker.error && (
                  <div className="flex items-start gap-3 rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
                    <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
                    <p>{tracker.error instanceof Error ? tracker.error.message : "Tracker data is unavailable."}</p>
                  </div>
                )}
                {latest && <MilestoneTracker latest={latest} history={history} />}
              </>
            )}

            {view !== "milestones" && (
              <SolanaPanel>
                {view === "payments" ? <LazyPaymentsTab /> : <LazyCoinForgeTab />}
              </SolanaPanel>
            )}
          </div>
        </main>
      </div>
    </RequireCustomer>
  );
}
