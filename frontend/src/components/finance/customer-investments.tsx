import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { useCustomerSession } from "@/lib/customer-session";
import { money, pct } from "@/lib/finance-api";
import { allocationAmounts, editableInvestmentProfile, investmentProjection, loadCustomerPortfolio, previewCustomerPortfolio,
  type CustomerPortfolio, type PortfolioAssessment } from "@/lib/customer-portfolio";

function Control({ label, value, min = 0, max, step = 1, onChange, format = String }: {
  label: string; value: number; min?: number; max: number; step?: number;
  onChange: (value: number) => void; format?: (value: number) => string;
}) {
  return <label className="block space-y-2 text-sm">
    <span className="flex justify-between gap-4"><span>{label}</span><strong>{format(value)}</strong></span>
    <input aria-label={label} type="range" className="w-full accent-[var(--primary)]" min={min} max={max}
      step={step} value={value} disabled={max <= min} onChange={(event) => onChange(Number(event.target.value))} />
  </label>;
}

export function CustomerInvestments() {
  const session = useCustomerSession();
  const query = useQuery({ queryKey: ["customer-investments", session?.email, session?.token],
    queryFn: loadCustomerPortfolio, enabled: Boolean(session?.token) && !session?.isStaff, retry: false });
  if (query.error) return <p role="alert" className="text-destructive">{query.error instanceof Error ? query.error.message : "Investments are unavailable."}</p>;
  if (!query.data) return <p>Loading your investments...</p>;
  return <InvestmentWorkspace key={`${session?.email}:${query.data.client_id}`} portfolio={query.data} />;
}

export function InvestmentWorkspace({ portfolio }: { portfolio: CustomerPortfolio }) {
  const [tab, setTab] = useState<"overview" | "risk" | "profile" | "rebalance">("overview");
  const [principal, setPrincipal] = useState(portfolio.value_cents / 100);
  const [monthly, setMonthly] = useState(0);
  const [assumedReturn, setAssumedReturn] = useState(5);
  const [profile, setProfile] = useState(() => editableInvestmentProfile(portfolio.profile));
  const [stocks, setStocks] = useState(Number((portfolio.allocations.stocks * 100).toFixed(4)));
  const [foreign, setForeign] = useState(Number((portfolio.allocations.foreign * 100).toFixed(4)));
  const [assessment, setAssessment] = useState<PortfolioAssessment>(portfolio.assessment);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const allocations = useMemo(() => ({ stocks: Number((stocks / 100).toFixed(6)), foreign: Number((foreign / 100).toFixed(6)),
    bonds: Number(((100 - stocks - foreign) / 100).toFixed(6)) }), [stocks, foreign]);
  const projection = useMemo(() => investmentProjection(principal, monthly, assumedReturn / 100, profile.horizon_months),
    [principal, monthly, assumedReturn, profile.horizon_months]);

  useEffect(() => {
    const controller = new AbortController();
    setPending(true);
    setError(null);
    if (profile.goal.trim().length < 3) {
      setPending(false);
      setError("Enter at least three characters for the scenario investment goal.");
      return () => controller.abort();
    }
    const timer = window.setTimeout(() => {
      void previewCustomerPortfolio({ allocations, profile, investment_cents: Math.round(principal * 100) }, controller.signal)
        .then((result) => { if (!controller.signal.aborted) setAssessment(result.assessment); })
        .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Preview unavailable"); })
        .finally(() => { if (!controller.signal.aborted) setPending(false); });
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [allocations, profile, principal]);

  const reset = () => {
    setPrincipal(portfolio.value_cents / 100); setMonthly(0); setAssumedReturn(5); setProfile(editableInvestmentProfile(portfolio.profile));
    setStocks(Number((portfolio.allocations.stocks * 100).toFixed(4)));
    setForeign(Number((portfolio.allocations.foreign * 100).toFixed(4)));
  };
  const controls = <div className="grid gap-5 sm:grid-cols-2">
    <Control label="Investment amount" value={principal} max={Math.max(100000, portfolio.value_cents / 100)} step={100} onChange={setPrincipal} format={money} />
    <Control label="Monthly investment contribution" value={monthly} max={5000} step={25} onChange={setMonthly} format={money} />
    <Control label="Investment horizon (months)" value={profile.horizon_months} min={1} max={600}
      onChange={(value) => setProfile({ ...profile, horizon_months: value })} />
    <Control label="Assumed annual return" value={assumedReturn} min={-20} max={20} step={0.5}
      onChange={setAssumedReturn} format={(value) => `${value}%`} />
  </div>;
  const scenarioRows = projection.points.filter((_, index, rows) => index === 0 || index === rows.length - 1 || index % Math.max(1, Math.floor(rows.length / 36)) === 0);
  const metricText = (value: number) => pending ? "Updating..." : error ? "Unavailable" : pct(value);
  const suggestion = assessment.profile_model;
  const recordedAmounts = allocationAmounts(portfolio.value_cents, portfolio.allocations);
  const suggestedAmounts = suggestion ? allocationAmounts(portfolio.value_cents, suggestion.allocations) : null;

  return <section className="space-y-6 pb-8">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <nav aria-label="Customer investment sections" className="flex flex-wrap gap-2">
        {([ ["overview", "Overview"], ["risk", "Risk & Return"], ["profile", "Profile"], ["rebalance", "Rebalancing"] ] as const).map(([id, label]) =>
          <Button key={id} variant={tab === id ? "default" : "outline"} onClick={() => setTab(id)}>{label}</Button>)}
      </nav>
      <Button variant="ghost" onClick={reset}>Reset what-if</Button>
    </div>
    <p className="text-xs text-muted-foreground">Your account's modeled portfolio, as of {portfolio.as_of}. Sliders preview scenarios; they do not trade or change your saved profile.</p>
    {tab === "overview" && <>
      <div className="grid gap-4 sm:grid-cols-3">
        <Metric label="Recorded portfolio" value={money(portfolio.value_cents / 100)} />
        <Metric label="Scenario ending value" value={money(projection.ending)} />
        <Metric label="Scenario contributions" value={money(projection.contributed)} />
      </div>
      {controls}
      <InvestmentChart title="Projection under your assumed return" rows={scenarioRows}
        lines={[{ key: "Balance", label: "Scenario value", color: "var(--primary)" }, { key: "Contributions", label: "Contributions", color: "#999" }]} />
      <p className="text-xs text-muted-foreground">Monthly compounding with contributions at month end, before fees and taxes. Assumed return is an editable scenario, not a prediction or guaranteed return.</p>
      <div className="grid gap-3 sm:grid-cols-3">{portfolio.holdings.map((holding) =>
        <Metric key={holding.bucket} label={holding.instrument} value={money(holding.value_cents / 100)} />)}</div>
    </>}
    {tab === "risk" && <>
      <div className="grid gap-5 sm:grid-cols-2">
        <Control label="Domestic stocks" value={stocks} max={100} format={(value) => `${value}%`} onChange={(value) => { setStocks(value); setForeign(Math.min(foreign, 100 - value)); }} />
        <Control label="Foreign equities" value={foreign} max={100 - stocks} format={(value) => `${value}%`} onChange={setForeign} />
      </div>
      <p className="text-sm">Scenario mix: {stocks}% domestic stocks + {100 - stocks - foreign}% bonds + {foreign}% foreign equities = 100%.</p>
      <div aria-busy={pending} className="grid gap-4 sm:grid-cols-4">
        <Metric label="Modeled annual return" value={metricText(assessment.metrics.annualized_return)} />
        <Metric label="Annualized volatility" value={metricText(assessment.metrics.volatility)} />
        <Metric label="Maximum drawdown" value={metricText(assessment.metrics.max_drawdown)} />
        <Metric label="Profile risk budget" value={metricText(assessment.risk_budget)} />
      </div>
      {!pending && !error && <InvestmentChart title="Historical replay of the scenario mix" rows={assessment.return_history}
        lines={[{ key: "portfolio_index", label: "Scenario mix", color: "var(--primary)" }, { key: "benchmark_index", label: "Benchmark", color: "#999" }]} />}
      <p className="text-xs text-muted-foreground">Synthetic historical index starting at 100. Changing the mix recalculates its historical replay; it does not change your actual holdings.</p>
    </>}
    {tab === "profile" && <>
      <label className="block text-sm">Scenario investment goal
        <input aria-label="Scenario investment goal" maxLength={200} className="mt-2 w-full rounded-lg border border-border bg-background p-3"
          value={profile.goal} onChange={(event) => setProfile({ ...profile, goal: event.target.value })} />
      </label>
      <div className="grid gap-5 sm:grid-cols-2">
        <Control label="Profile horizon (months)" value={profile.horizon_months} min={1} max={600} onChange={(value) => setProfile({ ...profile, horizon_months: value })} />
        <Control label="Risk tolerance" value={profile.tolerance} min={1} max={5} onChange={(value) => setProfile({ ...profile, tolerance: value })} format={(value) => `${value} / 5`} />
        <Control label="Liquidity reserve" value={profile.liquidity_need_cents / 100} max={Math.max(100000, portfolio.profile.liquidity_need_cents / 100)} step={100}
          onChange={(value) => setProfile({ ...profile, liquidity_need_cents: Math.round(value * 100) })} format={money} />
        <Control label="Target annual return" value={profile.target_return * 100} max={30} step={0.5}
          onChange={(value) => setProfile({ ...profile, target_return: value / 100 })} format={(value) => `${value}%`} />
      </div>
      <p aria-live="polite" className="text-sm">{pending ? "Updating profile scenario..." : error ? "Profile preview unavailable." : `Risk budget: ${pct(assessment.risk_budget)}. Binding limits: ${assessment.binding_limits.join(", ").replaceAll("_", " ")}.`}</p>
      <p className="text-xs text-muted-foreground">The horizon, tolerance, liquidity reserve and financial capacity jointly limit the risk budget. Raising a target does not guarantee higher returns.</p>
    </>}
    {tab === "rebalance" && <section aria-label="Portfolio rebalancing suggestions" aria-busy={pending} className="space-y-5">
      <div>
        <h2 className="font-display text-xl font-bold">A suggested mix for your portfolio</h2>
        <p className="mt-2 text-sm text-muted-foreground">Compare your recorded holdings with a mix selected for your risk budget and goal. Suggestions follow the current what-if profile; reset what-if to use your recorded settings.</p>
      </div>
      {pending ? <p role="status">Updating rebalancing suggestions...</p> : error ? <p>Rebalancing suggestions are unavailable until the preview loads successfully.</p>
        : !suggestion || !suggestedAmounts ? <p>No suggested mix is available within the model's constraints. Review your profile, risk settings and any missing financial inputs.</p>
        : <>
          <p className="rounded-2xl border border-primary/30 bg-primary/5 p-4 text-sm">
            {suggestion.same_as_current ? "The model suggests keeping your current scenario mix."
              : `This mix aims to keep modeled volatility within your ${pct(assessment.risk_budget)} risk budget.`}
            {suggestion.goal_feasible ? " Its modeled annual return meets your scenario target."
              : " The search did not find a mix meeting your return target within this risk budget. The displayed mix has the highest modeled return among the eligible choices."}
          </p>
          <div className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full text-left text-sm">
              <caption className="p-4 text-left text-xs text-muted-foreground">Allocation shifts illustrated using your recorded {money(portfolio.value_cents / 100)} portfolio value.</caption>
              <thead><tr className="border-b border-border"><th className="p-3">Investment</th><th className="p-3">Recorded mix</th><th className="p-3">Suggested mix</th><th className="p-3">Possible shift</th></tr></thead>
              <tbody>{([ ["stocks", "Domestic stocks"], ["bonds", "Bonds"], ["foreign", "Foreign equities"] ] as const).map(([bucket, label]) => {
                const shift = suggestedAmounts[bucket] - recordedAmounts[bucket];
                return <tr key={bucket} className="border-b border-border last:border-0">
                  <th scope="row" className="p-3 font-medium">{label}</th>
                  <td className="p-3">{pct(portfolio.allocations[bucket])}<span className="block text-xs text-muted-foreground">{money(recordedAmounts[bucket] / 100, 2)}</span></td>
                  <td className="p-3">{pct(suggestion.allocations[bucket])}<span className="block text-xs text-muted-foreground">{money(suggestedAmounts[bucket] / 100, 2)}</span></td>
                  <td className="p-3">{shift === 0 ? "Keep" : `${shift > 0 ? "Add" : "Reduce"} ${money(Math.abs(shift) / 100, 2)}`}</td>
                </tr>;
              })}</tbody>
            </table>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Metric label="Suggested modeled annual return" value={pct(suggestion.metrics.annualized_return)} />
            <Metric label="Suggested volatility" value={pct(suggestion.metrics.volatility)} />
            <Metric label="Suggested maximum drawdown" value={pct(suggestion.metrics.max_drawdown)} />
          </div>
          <p className="text-sm text-muted-foreground">Volatility describes how widely values fluctuate. Drawdown is the largest drop in the historical replay. The model searches mixes in five percentage-point steps, limits each bucket to eighty percent, and prefers smaller changes when a mix can meet the goal. Its risk budget follows {assessment.binding_limits.join(", ").replaceAll("_", " ")}.</p>
          <Button onClick={() => { setStocks(suggestion.allocations.stocks * 100); setForeign(suggestion.allocations.foreign * 100); setTab("risk"); }}>Preview suggested mix</Button>
          <p className="text-xs text-muted-foreground">This is a read-only suggestion. Previewing changes scenario sliders only. Fees, taxes and trading costs are excluded; your holdings stay unchanged.</p>
        </>}
    </section>}
    {error && <p role="alert" className="text-destructive">{error}</p>}
    {!pending && !error && assessment.flags.length > 0 && <p className="text-xs text-muted-foreground">Scenario review: {assessment.flags.join(", ").replaceAll("_", " ")}</p>}
    <p className="text-xs text-muted-foreground">{portfolio.disclaimer}</p>
  </section>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="rounded-2xl border border-border p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-2 text-xl font-bold tabular-nums">{value}</p></div>;
}
function InvestmentChart({ title, rows, lines }: { title: string; rows: object[]; lines: { key: string; label: string; color: string }[] }) {
  return <section className="rounded-2xl border border-border p-4"><h3 className="mb-3 font-bold">{title}</h3><div className="h-64">
    <ResponsiveContainer width="100%" height="100%"><LineChart data={rows}>
      <XAxis dataKey={"date" in (rows[0] ?? {}) ? "date" : "label"} /><YAxis /><Tooltip />
      {lines.map((line) => <Line key={line.key} dataKey={line.key} name={line.label} stroke={line.color} dot={false} isAnimationActive={false} />)}
    </LineChart></ResponsiveContainer>
  </div></section>;
}
