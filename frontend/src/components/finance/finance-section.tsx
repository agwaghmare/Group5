import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { useCustomerSession } from "@/lib/customer-session";
import { loadTracker, money, num, pct, type Snapshot } from "@/lib/finance-api";

export type FinanceView = "money" | "bills" | "goals" | "health";

const NAV: { id: FinanceView; label: string }[] = [
  { id: "money", label: "My Money" },
  { id: "bills", label: "Bills" },
  { id: "goals", label: "Savings" },
  { id: "health", label: "Loans & Health" },
];

export function FinanceSection({
  view,
  onViewChange,
}: {
  view: FinanceView;
  onViewChange: (v: FinanceView) => void;
}) {
  const session = useCustomerSession();
  const tracker = useQuery({
    queryKey: ["finance", "tracker", session?.email, session?.token],
    queryFn: loadTracker,
    enabled: Boolean(session?.token) && !session?.isStaff,
    retry: false,
  });
  const latest = tracker.data?.snapshots.at(-1);
  const history = tracker.data?.snapshots ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border/50 pb-4">
        <nav className="flex flex-wrap gap-2" aria-label="Finance sections">
          {NAV.map((item) => (
            <Button key={item.id} type="button" variant={view === item.id ? "default" : "outline"} onClick={() => onViewChange(item.id)}>
              {item.label}
            </Button>
          ))}
        </nav>
        <span className="rounded-full border border-primary/40 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-primary">
          Synthetic tracker{tracker.data ? ` · ${tracker.data.customer_id}` : ""}
        </span>
      </div>

      {session?.isStaff && (
        <p className="text-sm text-muted-foreground">This desk is for a customer tracker account. Sign in with a customer email to see balances.</p>
      )}
      {!session?.isStaff && tracker.isLoading && <div className="h-40 animate-pulse rounded-2xl bg-secondary/50" />}
      {!session?.isStaff && tracker.error && (
        <div className="flex items-start gap-3 rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
          <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
          <p>{tracker.error instanceof Error ? tracker.error.message : "Tracker data is unavailable."}</p>
        </div>
      )}
      {latest && view === "money" && <MoneyView latest={latest} history={history} />}
      {latest && view === "bills" && <BillsView latest={latest} />}
      {latest && view === "goals" && <GoalsView latest={latest} />}
      {latest && view === "health" && <HealthView latest={latest} />}
    </div>
  );
}

function MoneyView({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const [extraSave, setExtraSave] = useState(0);
  const available = num(latest.available_balance);
  const projected = num(latest.projected_balance_30d) - extraSave;
  const maxBar = Math.max(...history.map((row) => num(row.monthly_income)), 1);

  return (
    <div className="space-y-10 pb-10">
      <section>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Available on {latest.date}</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold tracking-tight md:text-5xl">
          {money(available - extraSave)}{" "}
          <span className="font-sans text-2xl font-normal text-muted-foreground md:text-3xl">after extra savings</span>
        </h2>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Balances come from the synthetic personal-finance tracker for this email. They are monthly observations, not live bank accounts.
        </p>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Checking" value={money(latest.checking_balance)} />
        <Stat label="Savings" value={money(latest.savings_balance)} detail={`${num(latest.savings_apy).toFixed(2)}% APY`} />
        <Stat label="Portfolio" value={money(latest.portfolio_value)} detail={`${num(latest.equity_allocation_pct).toFixed(0)}% equity`} />
        <Stat label="Home equity" value={money(latest.home_equity)} detail={num(latest.home_value) > 0 ? `Home ${money(latest.home_value)}` : "No home value recorded"} />
      </section>
      <section className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
        <div>
          <p className="mb-4 text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Income by month</p>
          <div className="flex h-40 items-end gap-1.5">
            {history.map((row) => (
              <div key={row.date} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <div className="w-full rounded-t-md bg-primary/80" style={{ height: `${Math.max(8, (num(row.monthly_income) / maxBar) * 100)}%` }} title={`${row.date} ${money(row.monthly_income)}`} />
                <span className="text-[9px] text-muted-foreground">{row.date.slice(5, 7)}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-2xl border border-border p-5">
          <MoneySlider label="Extra monthly savings" value={extraSave} min={0} max={2000} step={25} onChange={setExtraSave} />
          <p className="mt-4 text-sm text-muted-foreground">
            Tracker projected balance in 30 days is {money(latest.projected_balance_30d)}. After this extra transfer it would be about {money(projected)}. Income this month is {money(latest.monthly_income)} ({latest.pay_frequency}).
          </p>
        </div>
      </section>
    </div>
  );
}

function BillsView({ latest }: { latest: Snapshot }) {
  const income = num(latest.monthly_income);
  const bills = num(latest.recurring_bill_total);
  const subs = num(latest.subscription_cost_monthly);
  const debt = num(latest.minimum_debt_payment);
  const [cut, setCut] = useState(0);
  const committed = Math.max(0, bills + subs + debt - cut);
  const left = income - committed;

  return (
    <div className="space-y-8 pb-10">
      <section>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Committed this month</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold md:text-5xl">{money(committed)}</h2>
        <p className="mt-3 max-w-xl text-muted-foreground">
          {money(left)} of {money(income)} income remains after bills, subscriptions, and the minimum debt payment.
        </p>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Recurring bills" value={money(bills)} />
        <Stat label="Subscriptions" value={money(subs)} />
        <Stat label="Minimum debt" value={money(debt)} />
        <Stat label="Delays / overdrafts" value={`${num(latest.bill_payment_delay_count)} / ${num(latest.overdraft_count_90d)}`} detail="Delays this snapshot · overdrafts in 90 days" />
      </section>
      <div className="max-w-lg rounded-2xl border border-border p-5">
        <MoneySlider label="Bills you could trim" value={cut} min={0} max={Math.max(100, Math.round(bills + subs))} step={10} onChange={setCut} />
        <p className="mt-4 text-sm text-muted-foreground">
          Budget variance on this snapshot is {num(latest.budget_variance_pct).toFixed(1)}%. Life event recorded: {latest.life_event_type || "none"}.
        </p>
      </div>
    </div>
  );
}

function GoalsView({ latest }: { latest: Snapshot }) {
  const current = num(latest.emergency_fund_months);
  const savings = num(latest.savings_balance);
  const contribution = num(latest.monthly_savings_contribution);
  const [target, setTarget] = useState(Math.max(6, Math.ceil(current)));
  const [monthly, setMonthly] = useState(Math.round(contribution));
  const gapMonths = Math.max(0, target - current);
  const monthlyBurn = current > 0 ? savings / current : num(latest.monthly_income);
  const dollarsShort = gapMonths * monthlyBurn;
  const monthsToTarget = monthly > 0 ? Math.ceil(dollarsShort / monthly) : null;

  return (
    <div className="space-y-8 pb-10">
      <section>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Emergency fund</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold md:text-5xl">
          {current.toFixed(1)} <span className="font-sans text-2xl font-normal text-muted-foreground">months covered</span>
        </h2>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Savings balance {money(savings)}. Streak {num(latest.savings_streak_months)} months. Retirement contribution {money(latest.retirement_contribution)} this snapshot.
        </p>
      </section>
      <div className="h-3 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, (current / Math.max(target, 1)) * 100)}%` }} />
      </div>
      <div className="grid max-w-3xl gap-6 rounded-2xl border border-border p-5 md:grid-cols-2">
        <MoneySlider label="Target coverage" value={target} min={1} max={12} step={1} suffix=" mo" onChange={setTarget} />
        <MoneySlider label="Monthly contribution" value={monthly} min={0} max={2000} step={25} onChange={setMonthly} />
      </div>
      <p className="max-w-xl text-sm text-muted-foreground">
        {monthsToTarget === null
          ? "Set a contribution above zero to estimate the wait."
          : gapMonths === 0
            ? "This snapshot already meets that coverage."
            : `About ${money(dollarsShort)} short. At ${money(monthly)} a month, that is roughly ${monthsToTarget} ${monthsToTarget === 1 ? "month" : "months"}. This divides the gap by the contribution; it does not compound the ${num(latest.savings_apy).toFixed(2)}% APY.`}
      </p>
    </div>
  );
}

function HealthView({ latest }: { latest: Snapshot }) {
  const balance = num(latest.total_debt_balance);
  const minimum = num(latest.minimum_debt_payment);
  const [extra, setExtra] = useState(0);
  const [apr, setApr] = useState(Math.round(num(latest.weighted_avg_apr) * 2) / 2);
  const payment = minimum + extra;
  const months = useMemo(() => payoffMonths(balance, payment, apr), [balance, payment, apr]);
  const utilization = num(latest.credit_utilization);
  const runway = num(latest.liquidity_runway_months);

  return (
    <div className="space-y-8 pb-10">
      <section>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Debt on this snapshot</p>
        <h2 className="mt-3 font-display text-4xl font-extrabold md:text-5xl">{money(balance)}</h2>
        <p className="mt-3 max-w-xl text-muted-foreground">
          {months === null
            ? "The payment does not cover interest at this rate, so the balance would not fall."
            : `About ${months} months to clear it at ${money(payment)} a month and ${apr.toFixed(1)}% APR. Recorded remaining term is ${num(latest.remaining_loan_term_months)} months.`}
        </p>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Credit use" value={pct(utilization)} detail={utilization > 0.6 ? "Above 60%" : utilization > 0.3 ? "Above 30%" : "At or under 30%"} />
        <Stat label="Card APR" value={`${num(latest.credit_card_apr).toFixed(2)}%`} detail={`Limit ${money(latest.credit_limit_total)}`} />
        <Stat label="Mortgage" value={money(latest.mortgage_balance)} detail={`${num(latest.mortgage_interest_rate).toFixed(2)}% rate`} />
        <Stat label="Runway" value={`${runway.toFixed(1)} mo`} detail={`${num(latest.late_payments_12m)} late payments in 12 months`} />
      </section>
      <div className="grid max-w-3xl gap-6 rounded-2xl border border-border p-5 md:grid-cols-2">
        <MoneySlider label="Extra monthly payment" value={extra} min={0} max={1000} step={25} onChange={setExtra} />
        <MoneySlider label="APR to try" value={apr} min={0} max={24} step={0.5} suffix="%" onChange={setApr} />
      </div>
      <p className="text-sm text-muted-foreground">
        Debt service coverage on the tracker is {num(latest.debt_service_coverage).toFixed(2)}. The payoff count is a fixed-payment estimate from the balance, the rate you set, and the payment. It is not a loan offer.
      </p>
    </div>
  );
}

function payoffMonths(balance: number, payment: number, apr: number): number | null {
  if (balance <= 0) return 0;
  if (payment <= 0) return null;
  const monthlyRate = apr / 100 / 12;
  if (monthlyRate === 0) return Math.ceil(balance / payment);
  const interest = balance * monthlyRate;
  if (payment <= interest) return null;
  const months = -Math.log(1 - (balance * monthlyRate) / payment) / Math.log(1 + monthlyRate);
  return Math.ceil(months);
}

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="rounded-2xl border border-border px-4 py-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
      <p className="mt-2 font-display text-2xl font-extrabold">{value}</p>
      {detail && <p className="mt-1 text-xs text-muted-foreground">{detail}</p>}
    </div>
  );
}

function MoneySlider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  suffix = "",
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  onChange: (value: number) => void;
  suffix?: string;
}) {
  const shown = suffix === "%" || suffix === " mo" ? `${value}${suffix}` : money(value, 0);
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between gap-3">
        <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
        <span className="font-display text-sm font-bold tabular-nums text-primary">{shown}</span>
      </div>
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={(next) => onChange(next[0] ?? min)} aria-label={label} />
    </div>
  );
}
