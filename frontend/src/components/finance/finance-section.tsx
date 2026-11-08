import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AssistantVoice } from "@/components/assistant-voice";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { CustomerInvestments } from "@/components/finance/customer-investments";
import { Textarea } from "@/components/ui/textarea";
import { useCustomerSession } from "@/lib/customer-session";
import { savingsTransfer, trimmedBills, savingsGoal, loanPlan, projectCash } from "@/lib/finance-scenarios";
import { askAmelia, loadTracker, money, num, pct, type Snapshot } from "@/lib/finance-api";

export type FinanceView = "money" | "bills" | "goals" | "health" | "whatif" | "investments";

export const VIEW_FEATURE: Record<FinanceView, string> = {
  money: "fin.profile",
  bills: "fin.moneyleaks",
  goals: "fin.moneymission",
  health: "fin.debt",
  whatif: "fin.futureyou",
  investments: "fin.investments",
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
  { id: "investments", label: "Investments" },
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
      {latest && view === "money" && <MoneyView key={`${latest.user_id}:${latest.date}`} latest={latest} history={history} />}
      {latest && view === "bills" && <BillsView key={`${latest.user_id}:${latest.date}`} latest={latest} history={history} />}
      {latest && view === "goals" && <GoalsView key={`${latest.user_id}:${latest.date}`} latest={latest} history={history} />}
      {latest && view === "health" && <HealthView key={`${latest.user_id}:${latest.date}`} latest={latest} />}
      {latest && view === "whatif" && <WhatIfView key={`${latest.user_id}:${latest.date}`} latest={latest} />}
      {view === "investments" && <CustomerInvestments />}
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
  const ask = (text: string, review = false) => {
    const trimmed = text.trim();
    if (!trimmed || inFlight.current) return;
    inFlight.current = true;
    const currentRequest = ++requestId.current;
    setPending(true);
    setError(null);
    // Picture and free-form coaching follow the active tab's authorized evidence.
    const isReview = review || /\bquick\s+(chat|review)\b|\breview\s+(of\s+)?my\s+finances\b/i.test(trimmed);
    const evidenceFeature = isReview || skill === "fin.profile" || skill === "fin.coach" ? featureId : skill;
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
    <aside className="flex h-full w-full flex-col overflow-y-auto border-border bg-background p-4 lg:w-80 lg:border-l">
      <p className="font-display text-lg font-extrabold">Amelia</p>
      <p className="text-xs text-muted-foreground">
        Explanations of your synthetic tracker. Not financial advice.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
      <Button type="button" variant="outline" className="mt-3" disabled={pending} onClick={() => {
        setSkill("fin.profile");
        ask(`Give me a quick review of my finances in ${tab}. Explain the key numbers in plain words, what they mean for me, and one useful next step.`, true);
      }}>Quick review of {tab}</Button>
      <p className="mt-2 text-xs text-muted-foreground">Ask for a “quick chat” or “quick review of my finances” to get a short report on this section. Enable Speak replies to hear it.</p>
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
      <div className="mt-4 min-h-32 flex-1 space-y-3 overflow-y-auto">
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
        className="mt-3 flex shrink-0 flex-col gap-2"
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
        <AssistantVoice assistant="Amelia" busy={pending} contextKey={featureId}
          onDraft={setQuestion} onQuestion={ask} reply={turns.at(-1)?.answer ?? ""} />
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
  const scenario = savingsTransfer(latest, extraSave);
  const maximum = Math.min(2000, Math.floor(scenario.transferable / 25) * 25);
  const rows = useMemo(() => {
    const past = history.map((row) => ({
      label: row.date.slice(2, 7),
      Checking: Math.round(num(row.checking_balance)),
      Savings: Math.round(num(row.savings_balance)),
    }));
    return [...past, ...savingsTransfer(latest, extraSave).points];
  }, [history, latest, extraSave]);

  return (
    <Desk
      eyebrow={`Available after transfer - snapshot ${latest.date}`}
      figure={money(scenario.available)}
      note={`After moving ${money(scenario.transfer)} from checking to savings. Projected available in 30 days: ${money(scenario.projected30d)}.`}
      sliders={<MoneySlider label="Extra monthly savings" value={scenario.transfer} min={0} max={maximum} step={25} onChange={setExtraSave} />}
      stats={[
        ["Checking", money(scenario.checking)],
        ["Savings", money(scenario.savings)],
        ["Portfolio", money(latest.portfolio_value)],
        ["Home equity", money(latest.home_equity)],
      ]}
    >
      <TrendChart
        title="Recorded history and monthly savings transfers"
        data={rows}
        lines={[
          { key: "Checking", color: "var(--primary)" },
          { key: "Savings", color: "var(--destructive)" },
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Cards show the first transfer in this what-if. Portfolio and home equity are unaffected by a checking-to-savings transfer.
        Available cash keeps the tracker's recorded difference from checking.
        Future points repeat the transfer until available cash is used up; they exclude future pay, spending, and interest.
        Recorded history stays unchanged. This does not move money in your account.
      </p>
    </Desk>
  );
}

function BillsView({ latest, history }: { latest: Snapshot; history: Snapshot[] }) {
  const income = num(latest.monthly_income);
  const debt = num(latest.minimum_debt_payment);
  const [cut, setCut] = useState(0);
  const plan = trimmedBills(latest, cut);
  const rows = useMemo(() => [
    ...history.map((row) => ({
      label: row.date.slice(2, 7), Bills: num(row.recurring_bill_total),
      Subscriptions: num(row.subscription_cost_monthly), Debt: num(row.minimum_debt_payment),
    })),
    { label: "What-if", Bills: plan.bills, Subscriptions: plan.subscriptions, Debt: plan.debt },
  ], [history, plan.bills, plan.subscriptions, plan.debt]);

  return (
    <Desk
      eyebrow="Committed this month"
      figure={money(plan.committed)}
      note={`${money(plan.remaining)} of ${money(income)} income remains after trimming ${money(plan.cut)} from bills and subscriptions. Minimum debt payments stay fixed.`}
      sliders={
        <MoneySlider label="Bills you could trim" value={plan.cut} min={0} max={Math.floor(plan.maximumCut / 10) * 10} step={10} onChange={setCut} />
      }
      stats={[
        ["Recurring bills", money(plan.bills)],
        ["Subscriptions", money(plan.subscriptions)],
        ["Minimum debt", money(debt)],
        ["Delays / overdrafts", `${num(latest.bill_payment_delay_count)} / ${num(latest.overdraft_count_90d)}`],
      ]}
    >
      <TrendChart
        title="Recorded bills and proposed monthly costs"
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
  const [target, setTarget] = useState(Math.min(12, Math.max(6, Math.ceil(current))));
  const [monthly, setMonthly] = useState(Math.min(2000, Math.max(0, Math.round(num(latest.monthly_savings_contribution) / 25) * 25)));
  const goal = savingsGoal(latest, target, monthly);
  const { monthlyBurn, dollarsShort, monthsToTarget } = goal;
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
      eyebrow="Current emergency coverage"
      figure={`${current.toFixed(1)} mo`}
      note={
        !goal.basisAvailable
          ? "Recorded expenses are missing, so coverage and time to target cannot be estimated."
          : monthsToTarget === 0
            ? "This snapshot already meets that coverage."
            : monthsToTarget === null
              ? "Set a contribution above zero to estimate the wait."
            : `${money(dollarsShort)} short. At ${money(monthly)} a month, about ${monthsToTarget} ${monthsToTarget === 1 ? "month" : "months"}.`
      }
      sliders={
        <>
          <MoneySlider label="Target coverage" value={target} min={1} max={12} step={1} suffix=" mo" onChange={setTarget} />
          <MoneySlider label="Monthly contribution" value={monthly} min={0} max={2000} step={25} onChange={setMonthly} />
        </>
      }
      stats={[
        ["Savings after one month", money(goal.afterOneMonth)],
        ["Target reserve", goal.basisAvailable ? money(goal.targetDollars) : "Unavailable"],
        ["Months to target", goal.basisAvailable ? (monthsToTarget === null ? "Set contribution" : String(monthsToTarget)) : "Unavailable"],
        ["Recorded APY", `${num(latest.savings_apy).toFixed(2)}%`],
      ]}
    >
      <TrendChart
        title="Recorded savings and contribution-only projection"
        data={rows}
        lines={[
          { key: "Savings", color: "var(--primary)" },
          { key: "Target", color: "var(--destructive)" },
        ]}
      />
      <p className="text-xs text-muted-foreground">
        Projections add the selected contribution each month and exclude interest and withdrawals.
        Current coverage and the recorded APY stay tied to the snapshot.
      </p>
    </Desk>
  );
}

function HealthView({ latest }: { latest: Snapshot }) {
  const income = num(latest.monthly_income);
  const living = num(latest.recurring_bill_total) + num(latest.subscription_cost_monthly);
  const debt = num(latest.total_debt_balance);
  const initialAmount = Math.max(0, debt);
  const initialApr = Math.max(0, num(latest.weighted_avg_apr));
  const recordedTerm = num(latest.remaining_loan_term_months);
  const initialMonths = recordedTerm > 0 ? Math.round(recordedTerm) : 48;
  const [amount, setAmount] = useState(initialAmount);
  const [apr, setApr] = useState(initialApr);
  const [months, setMonths] = useState(initialMonths);
  const [extra, setExtra] = useState(0);
  const [incomeCut, setIncomeCut] = useState(0);

  const plan = useMemo(
    () => loanPlan(amount, apr, months, extra, income * (1 - incomeCut / 100), living),
    [amount, apr, months, extra, income, incomeCut, living],
  );

  return (
    <Desk
      eyebrow="Monthly loan payment including extra"
      figure={money(plan.totalPayment, 0)}
      note={plan.payoff === null ? "This payment does not cover interest, so the balance would not fall." : `${money(plan.interest)} total interest · payoff in ${plan.payoff} months.`}
      sliders={
        <>
          <MoneySlider label="Loan amount" value={amount} min={0} max={Math.max(50000, initialAmount)} step={100} onChange={setAmount} />
          <MoneySlider label="APR" value={apr} min={0} max={Math.max(24, initialApr)} step={0.1} suffix="%" onChange={setApr} />
          <MoneySlider label="Loan months" value={months} min={1} max={Math.max(84, initialMonths)} step={1} suffix=" mo" onChange={setMonths} />
          <MoneySlider label="Extra monthly payment" value={extra} min={0} max={1000} step={25} onChange={setExtra} />
          <MoneySlider label="Income reduction" value={incomeCut} min={0} max={80} step={5} suffix="%" onChange={setIncomeCut} />
        </>
      }
      stats={[
        ["Total interest", money(plan.interest)],
        ["Scheduled payment / income", plan.dti === null ? "—" : pct(plan.dti)],
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
        This what-if models one fixed-rate loan using recorded debt, rate, term, and income when available.
        It excludes fees and other loan payments. Extra payments reduce principal. It is not a credit offer.
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
      eyebrow="Lowest available balance"
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
        This simplified what-if spreads monthly bills and fixed minimum debt payments over thirty days and estimates paychecks
        from the recorded cadence. Higher living costs affect bills and subscriptions. Income cuts, an emergency, and payday
        delays affect the scenario; the baseline is unchanged.
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
      <Slider value={[value]} min={min} max={max > min ? max : min + step} disabled={max <= min} step={step} onValueChange={(next) => onChange(next[0] ?? min)} aria-label={label} />
    </div>
  );
}

function shortMoney(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1000) return `${value < 0 ? "-" : ""}$${Math.round(abs / 100) / 10}k`;
  return `$${Math.round(value)}`;
}
