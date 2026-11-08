import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Textarea } from "@/components/ui/textarea";
import { useCustomerSession } from "@/lib/customer-session";
import { askAmelia, loadTracker, money, num, pct, type Snapshot } from "@/lib/finance-api";

export type FinanceView = "money" | "bills" | "goals" | "health" | "whatif";

export const VIEW_FEATURE: Record<FinanceView, string> = {
  money: "fin.profile",
  bills: "fin.moneyleaks",
  goals: "fin.moneymission",
  health: "fin.debt",
  whatif: "fin.futureyou",
};

const AMELIA_SKILLS: { id: string; label: string }[] = [
  { id: "fin.profile", label: "Picture" },
  { id: "fin.xray", label: "X-Ray" },
  { id: "fin.futureyou", label: "FutureYou" },
  { id: "fin.moneymission", label: "Plan" },
  { id: "fin.immune", label: "Shock" },
  { id: "fin.moneyleaks", label: "Leaks" },
  { id: "fin.debt", label: "Debt" },
  { id: "fin.coach", label: "Coach" },
];

const NAV: { id: FinanceView; label: string }[] = [
  { id: "money", label: "My Money" },
  { id: "bills", label: "Bills" },
  { id: "goals", label: "Savings" },
  { id: "health", label: "Loans & Health" },
  { id: "whatif", label: "What If" },
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
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <nav className="flex flex-wrap gap-2" aria-label="Finance sections">
          {NAV.map((item) => (
            <Button key={item.id} type="button" size="sm" variant={view === item.id ? "default" : "outline"} onClick={() => onViewChange(item.id)}>
              {item.label}
            </Button>
          ))}
        </nav>
        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-muted-foreground">
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
      {latest && view === "bills" && <BillsView latest={latest} history={history} />}
      {latest && view === "goals" && <GoalsView latest={latest} history={history} />}
      {latest && view === "health" && <HealthView latest={latest} />}
      {latest && view === "whatif" && <WhatIfView latest={latest} />}
    </div>
  );
}

export function AmeliaRail({
  featureId,
  hint,
}: {
  featureId: string;
  hint: string;
}) {
  const [skill, setSkill] = useState("fin.profile");
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<{ question: string; answer: string }[]>([]);
  const requestId = useRef(0);
  const inFlight = useRef(false);
  const tab = NAV.find((item) => VIEW_FEATURE[item.id] === featureId)?.label ?? "Finance";
  const presetQuestions: Record<string, string> = {
    "fin.profile": `What is the current picture of the ${tab} tab, and what is going on? Explain the key numbers and what I should notice.`,
    "fin.xray": `Looking at ${tab}, what do my recorded financial health indicators mean, and which need attention?`,
    "fin.futureyou": `Looking at ${tab}, what do my recorded projections suggest about my future finances? Explain the assumptions and limitations.`,
    "fin.moneymission": `Looking at ${tab}, what practical savings and spending plan can I make from my recorded balances, income, and obligations?`,
    "fin.immune": `If I get a financial shock, what is my plan of action? Use my recorded income, bills, emergency fund, and reserves, with the ${tab} tab as context.`,
    "fin.moneyleaks": `Looking at ${tab}, where is money leaking through my recorded bills, subscriptions, or budget variance, and what should I review first?`,
    "fin.debt": `Looking at ${tab}, what do my recorded debts, interest rates, and payments mean, and what should I prioritize?`,
    "fin.coach": `Help me understand ${tab} in plain English. Based on my recorded finances, what should I focus on next and why?`,
  };
  useEffect(() => {
    requestId.current += 1;
    inFlight.current = false;
    setSkill("fin.profile");
    setQuestion("");
    setError(null);
    setTurns([]);
    setPending(false);
    return () => { requestId.current += 1; };
  }, [featureId]);
  const prompts = [
    { label: "What should I notice first?", skill: "fin.profile" },
    { label: "Do I still have an emergency cushion?", skill: "fin.immune" },
    { label: "Where is money leaking?", skill: "fin.moneyleaks" },
  ];
  const ask = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || inFlight.current) return;
    inFlight.current = true;
    const currentRequest = ++requestId.current;
    setPending(true);
    setError(null);
    // Picture and free-form coaching follow the active tab's authorized evidence.
    const evidenceFeature = skill === "fin.profile" || skill === "fin.coach" ? featureId : skill;
    void askAmelia(evidenceFeature, trimmed)
      .then((row) => {
        if (currentRequest !== requestId.current) return;
        setTurns((current) => [
          ...current,
          {
            question: trimmed,
            answer: [row.answer, ...row.reasons, ...row.limitations].join("\n\n"),
          },
        ]);
        setQuestion("");
      })
      .catch((err: unknown) => {
        if (currentRequest === requestId.current) setError(err instanceof Error ? err.message : "Amelia could not answer.");
      })
      .finally(() => {
        if (currentRequest === requestId.current) {
          inFlight.current = false;
          setPending(false);
        }
      });
  };
  return (
    <aside className="flex h-full w-full flex-col border-border bg-background p-4 lg:w-80 lg:border-l">
      <p className="font-display text-lg font-extrabold">Amelia</p>
      <p className="text-xs text-muted-foreground">
        Explanations of your synthetic tracker. Not financial advice.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {AMELIA_SKILLS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`rounded-full border px-3 py-1 text-left text-xs ${skill === item.id ? "border-primary text-primary" : "border-border hover:border-primary"}`}
            disabled={pending}
            aria-pressed={skill === item.id}
            onClick={() => {
              setSkill(item.id);
              setQuestion(presetQuestions[item.id] ?? "");
              setError(null);
            }}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-2">
        {prompts.map((prompt) => (
          <button
            key={prompt.label}
            type="button"
            className="rounded-full border border-border px-3 py-1 text-left text-xs hover:border-primary"
            disabled={pending}
            onClick={() => {
              setSkill(prompt.skill);
              setQuestion(`${prompt.label} Use my recorded finances, with the ${tab} tab as context.`);
              setError(null);
            }}
          >
            {prompt.label}
          </button>
        ))}
      </div>
      <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">Answers stay on this side of the desk.</p>
        )}
        {turns.map((turn, index) => (
          <article key={index} className="rounded-2xl border border-border p-3 text-sm">
            <p className="font-display font-bold">{turn.question}</p>
            <p className="mt-1 whitespace-pre-line text-muted-foreground">{turn.answer}</p>
          </article>
        ))}
      </div>
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <Textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask Amelia"
          aria-label="Ask Amelia"
          disabled={pending}
          rows={3}
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={pending || !question.trim()}>
          {pending ? "Asking…" : "Ask Amelia"}
        </Button>
      </form>
    </aside>
  );
}

function MoneyView({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const [extraSave, setExtraSave] = useState(0);
  const available = num(latest.available_balance) - extraSave;
  const rows = useMemo(() => {
    const past = history.map((row) => ({
      label: row.date.slice(2, 7),
      Checking: Math.round(num(row.checking_balance)),
      Savings: Math.round(num(row.savings_balance)),
    }));
    const checking = num(latest.checking_balance);
    const savings = num(latest.savings_balance);
    const ahead = Array.from({ length: 6 }, (_, index) => ({
      label: `+${index + 1}`,
      Checking: Math.round(checking - extraSave * (index + 1)),
      Savings: Math.round(savings + extraSave * (index + 1)),
    }));
    return [...past, ...ahead];
  }, [history, latest, extraSave]);

  return (
    <Desk
      eyebrow={`Available on ${latest.date}`}
      figure={money(available)}
      note={`After setting aside ${money(extraSave)}. Projected in 30 days: ${money(num(latest.projected_balance_30d) - extraSave)}.`}
      sliders={<MoneySlider label="Extra monthly savings" value={extraSave} min={0} max={2000} step={25} onChange={setExtraSave} />}
      stats={[
        ["Checking", money(latest.checking_balance)],
        ["Savings", money(latest.savings_balance)],
        ["Portfolio", money(latest.portfolio_value)],
        ["Home equity", money(latest.home_equity)],
      ]}
    >
      <TrendChart
        title="Balances on the tracker"
        data={rows}
        lines={[
          { key: "Checking", color: "var(--primary)" },
          { key: "Savings", color: "var(--destructive)" },
        ]}
      />
    </Desk>
  );
}

function BillsView({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const income = num(latest.monthly_income);
  const bills = num(latest.recurring_bill_total);
  const subs = num(latest.subscription_cost_monthly);
  const debt = num(latest.minimum_debt_payment);
  const [cut, setCut] = useState(0);
  const committed = Math.max(0, bills + subs + debt - cut);
  const rows = useMemo(
    () =>
      history.map((row) => ({
        label: row.date.slice(2, 7),
        Bills: Math.max(0, Math.round(num(row.recurring_bill_total) - cut)),
        Subscriptions: Math.round(num(row.subscription_cost_monthly)),
        Debt: Math.round(num(row.minimum_debt_payment)),
      })),
    [history, cut],
  );

  return (
    <Desk
      eyebrow="Committed this month"
      figure={money(committed)}
      note={`${money(income - committed)} of ${money(income)} income remains after bills, subscriptions, and the minimum debt payment.`}
      sliders={
        <MoneySlider label="Bills you could trim" value={cut} min={0} max={Math.max(100, Math.round(bills + subs))} step={10} onChange={setCut} />
      }
      stats={[
        ["Recurring bills", money(bills)],
        ["Subscriptions", money(subs)],
        ["Minimum debt", money(debt)],
        ["Delays / overdrafts", `${num(latest.bill_payment_delay_count)} / ${num(latest.overdraft_count_90d)}`],
      ]}
    >
      <TrendChart
        title="What the tracker recorded"
        data={rows}
        lines={[
          { key: "Bills", color: "var(--primary)" },
          { key: "Subscriptions", color: "oklch(0.75 0.12 200)" },
          { key: "Debt", color: "var(--destructive)" },
        ]}
      />
    </Desk>
  );
}

function GoalsView({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const current = num(latest.emergency_fund_months);
  const savings = num(latest.savings_balance);
  const [target, setTarget] = useState(Math.max(6, Math.ceil(current)));
  const [monthly, setMonthly] = useState(Math.round(num(latest.monthly_savings_contribution)));
  const gapMonths = Math.max(0, target - current);
  const monthlyBurn = current > 0 ? savings / current : num(latest.monthly_income);
  const dollarsShort = gapMonths * monthlyBurn;
  const monthsToTarget = monthly > 0 ? Math.ceil(dollarsShort / monthly) : null;
  const rows = useMemo(() => {
    const targetDollars = monthlyBurn * target;
    const past = history.map((row) => ({
      label: row.date.slice(2, 7),
      Savings: Math.round(num(row.savings_balance)),
      Target: Math.round(targetDollars),
    }));
    const ahead = Array.from({ length: 8 }, (_, index) => ({
      label: `+${index + 1}`,
      Savings: Math.round(savings + monthly * (index + 1)),
      Target: Math.round(targetDollars),
    }));
    return [...past, ...ahead];
  }, [history, savings, monthly, monthlyBurn, target]);

  return (
    <Desk
      eyebrow="Emergency fund"
      figure={`${current.toFixed(1)} mo`}
      note={
        monthsToTarget === null
          ? "Set a contribution above zero to estimate the wait."
          : gapMonths === 0
            ? "This snapshot already meets that coverage."
            : `${money(dollarsShort)} short. At ${money(monthly)} a month, about ${monthsToTarget} ${monthsToTarget === 1 ? "month" : "months"}.`
      }
      sliders={
        <>
          <MoneySlider label="Target coverage" value={target} min={1} max={12} step={1} suffix=" mo" onChange={setTarget} />
          <MoneySlider label="Monthly contribution" value={monthly} min={0} max={2000} step={25} onChange={setMonthly} />
        </>
      }
      stats={[
        ["Savings balance", money(savings)],
        ["Streak", `${num(latest.savings_streak_months)} mo`],
        ["APY", `${num(latest.savings_apy).toFixed(2)}%`],
        ["Retirement", money(latest.retirement_contribution)],
      ]}
    >
      <TrendChart
        title="Savings balance"
        data={rows}
        lines={[
          { key: "Savings", color: "var(--primary)" },
          { key: "Target", color: "var(--destructive)" },
        ]}
      />
    </Desk>
  );
}

function HealthView({ latest }: { latest: Snapshot }) {
  const income = num(latest.monthly_income);
  const living = num(latest.recurring_bill_total) + num(latest.subscription_cost_monthly);
  const [amount, setAmount] = useState(15000);
  const [apr, setApr] = useState(12);
  const [months, setMonths] = useState(48);
  const [extra, setExtra] = useState(0);
  const [incomeCut, setIncomeCut] = useState(0);
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    if (seeded) return;
    const debt = num(latest.total_debt_balance);
    setAmount(debt >= 500 ? Math.round(debt / 100) * 100 : 15000);
    setApr(Math.min(24, Math.max(0, Math.round(num(latest.weighted_avg_apr) * 2) / 2)));
    const term = num(latest.remaining_loan_term_months);
    setMonths(term >= 12 ? Math.min(84, Math.round(term / 6) * 6) : 48);
    setSeeded(true);
  }, [latest, seeded]);

  const plan = useMemo(
    () => loanPlan(amount, apr, months, extra, income * (1 - incomeCut / 100), living),
    [amount, apr, months, extra, income, incomeCut, living],
  );

  return (
    <Desk
      eyebrow="Contract payment"
      figure={money(plan.payment, 0)}
      note={plan.payoff === null ? "This payment does not cover interest, so the balance would not fall." : `${money(plan.interest)} total interest · payoff in ${plan.payoff} months.`}
      sliders={
        <>
          <MoneySlider label="Loan amount" value={amount} min={1000} max={50000} step={500} onChange={setAmount} />
          <MoneySlider label="APR" value={apr} min={0} max={24} step={0.5} suffix="%" onChange={setApr} />
          <MoneySlider label="Loan months" value={months} min={12} max={84} step={6} suffix=" mo" onChange={setMonths} />
          <MoneySlider label="Extra monthly payment" value={extra} min={0} max={1000} step={25} onChange={setExtra} />
          <MoneySlider label="Income reduction" value={incomeCut} min={0} max={80} step={5} suffix="%" onChange={setIncomeCut} />
        </>
      }
      stats={[
        ["Total interest", money(plan.interest)],
        ["Debt to income", plan.dti === null ? "—" : pct(plan.dti)],
        ["Monthly surplus", money(plan.surplus)],
        ["Payoff", plan.payoff === null ? "—" : `${plan.payoff} mo`],
      ]}
    >
      <TrendChart
        title="Remaining balance"
        data={plan.points}
        area={{ key: "Balance", color: "var(--primary)" }}
      />
      <p className="text-xs text-muted-foreground">
        Starts from this account’s debt, rate, term, and income. The payment is a standard fixed schedule plus any extra you add. It is not a credit offer.
      </p>
    </Desk>
  );
}

function WhatIfView({ latest }: { latest: Snapshot }) {
  const [scenario, setScenario] = useState<"normal" | "disruption" | "expense" | null>("normal");
  const [days, setDays] = useState(30);
  const [incomeCut, setIncomeCut] = useState(0);
  const [livingUp, setLivingUp] = useState(0);
  const [emergency, setEmergency] = useState(0);
  const [delay, setDelay] = useState(0);

  const apply = (next: "normal" | "disruption" | "expense") => {
    setScenario(next);
    if (next === "normal") {
      setDays(30);
      setIncomeCut(0);
      setLivingUp(0);
      setEmergency(0);
      setDelay(0);
    } else if (next === "disruption") {
      setDays(90);
      setIncomeCut(40);
      setLivingUp(0);
      setEmergency(0);
      setDelay(7);
    } else {
      setDays(60);
      setIncomeCut(0);
      setLivingUp(10);
      setEmergency(Math.min(10000, Math.round(num(latest.checking_balance) * 0.2)));
      setDelay(0);
    }
  };

  const forecast = useMemo(
    () => projectCash(latest, { days, incomeCut, livingUp, emergency, delay }),
    [latest, days, incomeCut, livingUp, emergency, delay],
  );

  return (
    <Desk
      eyebrow="Lowest balance"
      figure={money(forecast.lowest)}
      note={`Ending ${money(forecast.ending)}. First shortfall: ${forecast.shortfall ?? "none"}. Baseline keeps today’s income and bills.`}
      sliders={
        <>
          <div className="flex flex-wrap gap-2 sm:col-span-2">
            {(
              [
                ["normal", "Normal"],
                ["disruption", "Income disruption"],
                ["expense", "Unexpected expense"],
              ] as const
            ).map(([id, label]) => (
              <Button key={id} type="button" size="sm" variant={scenario === id ? "default" : "outline"} onClick={() => apply(id)}>
                {label}
              </Button>
            ))}
          </div>
          <MoneySlider label="Forecast days" value={days} min={14} max={120} step={1} suffix=" d" onChange={(value) => { setScenario(null); setDays(value); }} />
          <MoneySlider label="Income reduction" value={incomeCut} min={0} max={80} step={5} suffix="%" onChange={(value) => { setScenario(null); setIncomeCut(value); }} />
          <MoneySlider label="Living cost increase" value={livingUp} min={0} max={80} step={5} suffix="%" onChange={(value) => { setScenario(null); setLivingUp(value); }} />
          <MoneySlider label="One-time emergency" value={emergency} min={0} max={10000} step={100} onChange={(value) => { setScenario(null); setEmergency(value); }} />
          <MoneySlider label="Payday delay" value={delay} min={0} max={30} step={1} suffix=" d" onChange={(value) => { setScenario(null); setDelay(value); }} />
        </>
      }
      stats={[
        ["Starting cash", money(latest.available_balance)],
        ["Ending balance", money(forecast.ending)],
        ["First shortfall", forecast.shortfall ?? "None"],
        ["Pay cadence", latest.pay_frequency],
      ]}
    >
      <TrendChart
        title="The next chapter of your balance"
        data={forecast.points}
        lines={[
          { key: "Scenario", color: "var(--primary)" },
          { key: "Baseline", color: "var(--destructive)" },
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Each point spends a share of recorded bills and adds a paycheck on the tracker’s pay cadence. Income reduction, higher living costs, a one-time emergency, and a delayed paycheck change only the green line.
      </p>
    </Desk>
  );
}

function Desk({
  eyebrow,
  figure,
  note,
  sliders,
  stats,
  children,
}: {
  eyebrow: string;
  figure: string;
  note: string;
  sliders: ReactNode;
  stats: [string, string][];
  children: ReactNode;
}) {
  return (
    <div className="space-y-6 pb-8">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(16rem,0.8fr)_minmax(0,1.2fr)]">
        <div>
          <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-muted-foreground">{eyebrow}</p>
          <p className="mt-2 font-sans text-4xl font-semibold tabular-nums tracking-tight text-foreground md:text-5xl">{figure}</p>
          <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">{note}</p>
        </div>
        <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">{sliders}</div>
      </div>
      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-border bg-border md:grid-cols-4">
        {stats.map(([label, value]) => (
          <div key={label} className="bg-background px-4 py-3">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
            <p className="mt-1 font-sans text-lg font-medium tabular-nums text-foreground">{value}</p>
          </div>
        ))}
      </div>
      {children}
    </div>
  );
}

function TrendChart({
  title,
  data,
  lines,
  area,
}: {
  title: string;
  data: Record<string, string | number>[];
  lines?: { key: string; color: string }[];
  area?: { key: string; color: string };
}) {
  return (
    <section className="rounded-2xl border border-border px-3 py-4 md:px-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-2">
        <p className="text-sm font-medium">{title}</p>
        <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
          {(lines ?? (area ? [area] : [])).map((series) => (
            <span key={series.key} className="inline-flex items-center gap-1.5">
              <span className="size-2 rounded-full" style={{ background: series.color }} />
              {series.key}
            </span>
          ))}
        </div>
      </div>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          {area ? (
            <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="oklch(1 0 0 / 8%)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "oklch(0.65 0 0)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "oklch(0.65 0 0)", fontSize: 11 }} axisLine={false} tickLine={false} width={56} tickFormatter={(value) => shortMoney(Number(value))} />
              <Tooltip content={<ChartTip />} />
              <Area type="monotone" dataKey={area.key} stroke={area.color} fill={area.color} fillOpacity={0.18} strokeWidth={2} isAnimationActive animationDuration={500} animationEasing="ease-out" />
            </AreaChart>
          ) : (
            <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="oklch(1 0 0 / 8%)" vertical={false} />
              <XAxis dataKey="label" tick={{ fill: "oklch(0.65 0 0)", fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: "oklch(0.65 0 0)", fontSize: 11 }} axisLine={false} tickLine={false} width={56} tickFormatter={(value) => shortMoney(Number(value))} />
              <Tooltip content={<ChartTip />} />
              {lines?.map((series) => (
                <Line key={series.key} type="monotone" dataKey={series.key} stroke={series.color} strokeWidth={2} dot={false} isAnimationActive animationDuration={500} animationEasing="ease-out" />
              ))}
            </LineChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  );
}

function ChartTip({ active, payload, label }: { active?: boolean; payload?: { name: string; value: number; color: string }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-border bg-background px-3 py-2 text-xs shadow-glow">
      <p className="mb-1 text-muted-foreground">{label}</p>
      {payload.map((item) => (
        <p key={item.name} className="font-sans tabular-nums" style={{ color: item.color }}>
          {item.name}: {money(item.value)}
        </p>
      ))}
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
  const shown = suffix ? `${value}${suffix}` : money(value, 0);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <Label className="text-xs text-muted-foreground">{label}</Label>
        <span className="font-sans text-sm font-medium tabular-nums text-foreground">{shown}</span>
      </div>
      <Slider value={[value]} min={min} max={max} step={step} onValueChange={(next) => onChange(next[0] ?? min)} aria-label={label} />
    </div>
  );
}

function shortMoney(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1000) return `${value < 0 ? "-" : ""}$${Math.round(abs / 100) / 10}k`;
  return `$${Math.round(value)}`;
}

function payInterval(frequency: string) {
  const value = frequency.toLowerCase();
  if (value.includes("bi")) return 14;
  if (value.includes("week")) return 7;
  if (value.includes("semi")) return 15;
  return 30;
}

function projectCash(
  latest: Snapshot,
  input: { days: number; incomeCut: number; livingUp: number; emergency: number; delay: number },
) {
  const start = num(latest.available_balance);
  const monthlyIncome = num(latest.monthly_income);
  const monthlyLiving = num(latest.recurring_bill_total) + num(latest.subscription_cost_monthly) + num(latest.minimum_debt_payment);
  const interval = payInterval(latest.pay_frequency);
  const origin = new Date(`${latest.date}T00:00:00`);
  const walk = (shock: boolean) => {
    let balance = start - (shock ? input.emergency : 0);
    let lowest = balance;
    let shortfall: string | null = null;
    const points = [balance];
    const daily = (monthlyLiving / 30) * (shock ? 1 + input.livingUp / 100 : 1);
    const paycheck = (monthlyIncome / (30 / interval)) * (shock ? 1 - input.incomeCut / 100 : 1);
    const wait = shock ? input.delay : 0;
    for (let day = 1; day <= input.days; day += 1) {
      balance -= daily;
      if (day > wait && (day - wait) % interval === 0) balance += paycheck;
      if (balance < lowest) lowest = balance;
      if (balance < 0 && !shortfall) {
        const when = new Date(origin);
        when.setDate(when.getDate() + day);
        shortfall = `${when.getMonth() + 1}/${when.getDate()}`;
      }
      points.push(balance);
    }
    return { points, lowest, ending: balance, shortfall };
  };

  const scenario = walk(true);
  const baseline = walk(false);
  const slots = 16;
  return {
    lowest: scenario.lowest,
    ending: scenario.ending,
    shortfall: scenario.shortfall,
    points: Array.from({ length: slots }, (_, index) => {
      const day = Math.round((index / (slots - 1)) * input.days);
      const when = new Date(origin);
      when.setDate(when.getDate() + day);
      return {
        label: `${when.getMonth() + 1}/${when.getDate()}`,
        Scenario: Math.round(scenario.points[day] ?? scenario.ending),
        Baseline: Math.round(baseline.points[day] ?? baseline.ending),
      };
    }),
  };
}

function loanPlan(principal: number, apr: number, term: number, extra: number, income: number, living: number) {
  const rate = apr / 100 / 12;
  const payment = rate === 0 ? principal / term : (principal * rate * (1 + rate) ** term) / ((1 + rate) ** term - 1);
  let balance = principal;
  let interest = 0;
  let payoff: number | null = null;
  const series = [balance];
  for (let month = 1; month <= term + 240 && balance > 1; month += 1) {
    const charge = balance * rate;
    const due = payment + extra;
    if (due <= charge && rate > 0) break;
    const paid = Math.min(balance + charge, due);
    interest += Math.min(charge, paid);
    balance = Math.max(0, balance + charge - paid);
    if (balance <= 1) {
      balance = 0;
      payoff = month;
    }
    series.push(balance);
    if (balance === 0) break;
  }
  const slots = 24;
  const points = Array.from({ length: slots + 1 }, (_, index) => {
    const month = Math.round((index / slots) * term);
    return { label: String(month), Balance: Math.round(series[Math.min(month, series.length - 1)] ?? 0) };
  });
  return {
    payment,
    interest,
    payoff,
    dti: income > 0 ? payment / income : null,
    surplus: income - living - payment - extra,
    points,
  };
}
