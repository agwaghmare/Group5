import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertTriangle,
  ArrowRight,
  Building2,
  CalendarDays,
  ChevronDown,
  Landmark,
  PiggyBank,
  Target,
  Wallet,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  CUSTOMERS,
  financeApi,
  getStoredCustomerId,
  money,
  pct,
  setStoredCustomerId,
  statusTone,
  type Account,
  type EvidenceBlock,
  type Obligation,
} from "@/lib/finance-api";

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
  const [customerId, setCustomerId] = useState("C001");
  const qc = useQueryClient();

  useEffect(() => setCustomerId(getStoredCustomerId()), []);

  const switchCustomer = (id: string) => {
    setStoredCustomerId(id);
    setCustomerId(id);
    void qc.invalidateQueries({ queryKey: ["finance"] });
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4 border-b border-border/50 pb-4">
        <nav className="flex flex-wrap gap-6" aria-label="Finance sections">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onViewChange(item.id)}
              className={`font-display text-sm font-bold tracking-wide transition-colors ${
                view === item.id
                  ? "text-foreground"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {item.label}
              {view === item.id && (
                <span className="mt-2 block h-0.5 w-full bg-primary" />
              )}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3">
          <Select value={customerId} onValueChange={switchCustomer}>
            <SelectTrigger className="h-9 w-[140px] border-border/70 bg-transparent text-xs uppercase tracking-wider">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CUSTOMERS.map((id) => (
                <SelectItem key={id} value={id}>
                  {id}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <span className="hidden rounded-full border border-primary/40 px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.2em] text-primary sm:inline">
            Banking demo
          </span>
        </div>
      </div>

      {view === "money" && <MoneyView customerId={customerId} onViewChange={onViewChange} />}
      {view === "bills" && <BillsView customerId={customerId} />}
      {view === "goals" && <GoalsView customerId={customerId} />}
      {view === "health" && <HealthView customerId={customerId} />}
    </div>
  );
}

function useFinanceQuery<T>(
  key: string[],
  customerId: string,
  fn: () => Promise<T>,
  enabled = true,
) {
  return useQuery({
    queryKey: ["finance", customerId, ...key],
    queryFn: fn,
    staleTime: 30_000,
    enabled: enabled && Boolean(customerId),
  });
}

function LoadError({ error }: { error: Error | null }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-destructive" />
      <div>
        <p className="font-medium">Could not load from the PNC API</p>
        <p className="text-muted-foreground">{error.message}</p>
      </div>
    </div>
  );
}

function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse rounded-2xl bg-secondary/50 ${className}`} />;
}

// ------------------------------------------------------------------ My Money
function MoneyView({
  customerId,
  onViewChange,
}: {
  customerId: string;
  onViewChange: (v: FinanceView) => void;
}) {
  const [whyOpen, setWhyOpen] = useState(false);
  const profile = useFinanceQuery(["profile"], customerId, financeApi.profile);
  const accounts = useFinanceQuery(["accounts"], customerId, financeApi.accounts);
  const safe = useFinanceQuery(["safe"], customerId, financeApi.safeSpend);
  const cash = useFinanceQuery(["cash"], customerId, () => financeApi.cashFlow(6));
  const obligations = useFinanceQuery(["obligations"], customerId, () => financeApi.obligations(45));
  const forecast = useFinanceQuery(["forecast"], customerId, financeApi.forecast);

  const err = profile.error || accounts.error || safe.error;
  if (err) return <LoadError error={err as Error} />;
  if (safe.isLoading || accounts.isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-28" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-44" />
          <Skeleton className="h-44" />
        </div>
      </div>
    );
  }

  const safeBlock = safe.data as EvidenceBlock;
  const safeAmt = Number(safeBlock.results.safe_to_spend ?? 0);
  const bills = obligations.data?.obligations ?? [];
  const billCount = bills.length;
  const projected =
    forecast.data?.forecast?.[0]?.point !== undefined
      ? Number(accounts.data?.accounts.filter((a) => ["checking", "savings"].includes(a.account_type)).reduce((s, a) => s + Number(a.balance), 0) ?? 0) +
        Number(forecast.data.forecast[0].point)
      : null;

  const checking = accounts.data?.accounts.find((a) => a.account_type === "checking");
  const savings = accounts.data?.accounts.find((a) => a.account_type === "savings");
  const recurring = summarizeCommitments(bills);

  return (
    <div className="space-y-10 pb-10">
      <section>
        <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">
          Your money, at a glance
        </p>
        <h2 className="mt-3 font-display text-4xl font-extrabold tracking-tight md:text-5xl">
          {money(safeAmt)}{" "}
          <span className="font-sans text-2xl font-normal text-muted-foreground md:text-3xl">
            estimated safe to spend
          </span>
        </h2>
        <p className="mt-3 max-w-xl text-muted-foreground">
          Keep the reserve intact before adding new commitments
          {profile.data?.display_name ? ` — ${profile.data.display_name}` : ""}.
        </p>
        <p className="mt-4 text-sm text-muted-foreground">
          {projected !== null && (
            <>
              Modeled balance in 30 days:{" "}
              <span className="text-foreground">{money(projected)}</span>
              <span className="mx-2 text-border">·</span>
            </>
          )}
          Upcoming recurring bills: <span className="text-foreground">{billCount}</span>
        </p>
        <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <button type="button" className="text-primary hover:underline" onClick={() => onViewChange("bills")}>
            Make a payment
          </button>
          <span className="text-border">/</span>
          <button type="button" className="text-primary hover:underline" onClick={() => onViewChange("goals")}>
            Plan savings
          </button>
          <span className="text-border">/</span>
          <button type="button" className="text-primary hover:underline" onClick={() => onViewChange("health")}>
            Review debt
          </button>
          <button
            type="button"
            className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            onClick={() => setWhyOpen((v) => !v)}
          >
            Why this estimate? <ChevronDown className={`size-3.5 transition ${whyOpen ? "rotate-180" : ""}`} />
          </button>
        </div>
        {whyOpen && (
          <div className="mt-3 max-w-2xl rounded-xl border border-border/60 bg-secondary/30 px-4 py-3 text-xs text-muted-foreground">
            <p className="font-medium text-foreground">Safe spend formula</p>
            <ul className="mt-2 list-disc space-y-1 pl-4">
              {(safeBlock.formula_steps ?? []).map((s) => (
                <li key={s}>{s}</li>
              ))}
            </ul>
            <p className="mt-2">{safeBlock.assumptions?.[0]}</p>
          </div>
        )}
      </section>

      <section className="grid gap-4 md:grid-cols-2">
        {checking && <AccountCard account={checking} accent />}
        {savings && <AccountCard account={savings} />}
      </section>

      <section className="grid gap-3 md:grid-cols-3">
        <ActionRow icon={<Wallet className="size-4" />} label="Review cash flow" onClick={() => document.getElementById("cash-flow")?.scrollIntoView({ behavior: "smooth" })} />
        <ActionRow icon={<PiggyBank className="size-4" />} label="Plan your savings" onClick={() => onViewChange("goals")} />
        <ActionRow icon={<CalendarDays className="size-4" />} label="Manage recurring bills" onClick={() => onViewChange("bills")} />
      </section>

      <section className="grid gap-8 lg:grid-cols-2" id="cash-flow">
        <div>
          <h3 className="font-display text-xl font-extrabold">Recorded cash flow</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Income and consumption — last {cash.data?.months.length ?? 0} months
          </p>
          {cash.isLoading ? (
            <Skeleton className="mt-6 h-48" />
          ) : (
            <CashBars months={cash.data?.months ?? []} />
          )}
        </div>
        <div>
          <h3 className="font-display text-xl font-extrabold">Your recurring commitments</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Monthly amounts modeled in your financial plan
          </p>
          <ul className="mt-5 divide-y divide-border/50 border-y border-border/50">
            {recurring.map((row) => (
              <li key={row.label} className="flex items-baseline justify-between gap-4 py-3">
                <div>
                  <p className="font-medium">{row.label}</p>
                  <p className="text-xs text-muted-foreground">{row.detail}</p>
                </div>
                <p className="font-display text-lg font-bold tabular-nums">{money(row.amount, 0)}</p>
              </li>
            ))}
            {recurring.length === 0 && (
              <li className="py-4 text-sm text-muted-foreground">No recurring obligations on file.</li>
            )}
          </ul>
        </div>
      </section>
    </div>
  );
}

function AccountCard({ account, accent = false }: { account: Account; accent?: boolean }) {
  const last4 = account.account_id.replace(/\D/g, "").slice(-4) || "0000";
  return (
    <div
      className={`relative flex min-h-[11.5rem] flex-col justify-between overflow-hidden rounded-2xl p-5 ${
        accent
          ? "bg-primary text-primary-foreground shadow-glow"
          : "border border-border/70 bg-card"
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Building2 className={`size-4 ${accent ? "opacity-90" : "text-primary"}`} />
          <span className="font-display text-sm font-extrabold tracking-wide">FINPILOT</span>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-[10px] font-bold uppercase tracking-wider ${
            accent ? "bg-primary-foreground/15" : "border border-border bg-secondary/40"
          }`}
        >
          View
        </span>
      </div>
      <div>
        <p className={`text-xs uppercase tracking-wider ${accent ? "opacity-80" : "text-muted-foreground"}`}>
          {account.name}
        </p>
        <p className="mt-1 font-display text-3xl font-extrabold tabular-nums md:text-4xl">
          {money(account.balance, 2)}
        </p>
      </div>
      <div className="flex items-end justify-between text-xs">
        <span className={`tracking-widest ${accent ? "opacity-80" : "text-muted-foreground"}`}>
          •••• {last4}
        </span>
        <span className={`font-bold uppercase tracking-[0.2em] ${accent ? "opacity-80" : "text-muted-foreground"}`}>
          {account.account_type.replaceAll("_", " ")}
        </span>
      </div>
    </div>
  );
}

function ActionRow({
  icon,
  label,
  onClick,
}: {
  icon: ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex items-center justify-between rounded-xl border border-border/70 bg-transparent px-4 py-3 text-left text-sm font-medium transition hover:border-primary/50 hover:bg-secondary/30"
    >
      <span className="inline-flex items-center gap-3">
        <span className="text-primary">{icon}</span>
        {label}
      </span>
      <ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-primary" />
    </button>
  );
}

function CashBars({
  months,
}: {
  months: { month: string; income: string; consumption_spending: string }[];
}) {
  const max = Math.max(...months.map((m) => Math.max(Number(m.income), Number(m.consumption_spending))), 1);
  return (
    <div className="mt-6">
      <div className="flex h-48 items-end gap-2">
        {months.map((m) => (
          <div key={m.month} className="flex h-full flex-1 flex-col justify-end gap-1">
            <div className="flex flex-1 items-end gap-0.5">
              <div
                className="w-1/2 rounded-t bg-primary/85"
                style={{ height: `${(Number(m.income) / max) * 100}%` }}
                title={`Income ${money(m.income)}`}
              />
              <div
                className="w-1/2 rounded-t bg-destructive/70"
                style={{ height: `${(Number(m.consumption_spending) / max) * 100}%` }}
                title={`Spending ${money(m.consumption_spending)}`}
              />
            </div>
            <span className="truncate text-center text-[10px] text-muted-foreground">
              {m.month.slice(5, 7)}/{m.month.slice(2, 4)}
            </span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-primary/85" /> Income
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-destructive/70" /> Spending
        </span>
      </div>
    </div>
  );
}

function summarizeCommitments(bills: Obligation[]) {
  const groups = new Map<string, { amount: number; day: string; kind: string }>();
  for (const b of bills) {
    const label =
      b.kind === "housing"
        ? "Rent / housing"
        : b.kind === "utility"
          ? "Utilities"
          : b.kind === "subscription"
            ? "Subscriptions"
            : b.kind === "insurance"
              ? "Insurance"
              : b.kind === "debt_payment"
                ? "Debt payments"
                : b.kind.replaceAll("_", " ");
    const day = b.due.slice(8, 10);
    const cur = groups.get(label) ?? { amount: 0, day, kind: b.kind };
    cur.amount += Number(b.amount);
    groups.set(label, cur);
  }
  return [...groups.entries()]
    .map(([label, v]) => ({
      label,
      amount: v.amount,
      detail: v.kind === "debt_payment" ? "Existing debt payment" : `Due around day ${Number(v.day)}`,
    }))
    .sort((a, b) => b.amount - a.amount);
}

// ------------------------------------------------------------------ Bills
function BillsView({ customerId }: { customerId: string }) {
  const obligations = useFinanceQuery(["obligations"], customerId, () => financeApi.obligations(45));
  const [reminders, setReminders] = useState<Record<string, boolean>>({});

  if (obligations.error) return <LoadError error={obligations.error as Error} />;
  if (obligations.isLoading) return <Skeleton className="h-72" />;

  const bills = [...(obligations.data?.obligations ?? [])].sort((a, b) => a.due.localeCompare(b.due));
  const monthlyBills = bills
    .filter((b) => b.kind !== "debt_payment")
    .reduce((s, b) => s + Number(b.amount), 0);
  const debtService = bills
    .filter((b) => b.kind === "debt_payment")
    .reduce((s, b) => s + Number(b.amount), 0);
  const reminderCount = Object.values(reminders).filter(Boolean).length;

  return (
    <div className="space-y-8 pb-10">
      <div className="grid gap-4 md:grid-cols-3">
        <MetricTile label="Recurring monthly bills" value={money(monthlyBills, 0)} />
        <MetricTile label="Monthly debt service" value={money(debtService, 0)} />
        <MetricTile label="Reminders scheduled" value={String(reminderCount)} />
      </div>

      <section className="rounded-2xl border border-border/70 px-5 py-6 md:px-8">
        <h3 className="font-display text-2xl font-extrabold">Your obligation calendar</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          Known bills feed the deterministic cash-flow forecast.
        </p>
        <ul className="mt-6 divide-y divide-border/50">
          {bills.map((b, i) => {
            const key = `${b.kind}-${b.due}-${b.amount}-${i}`;
            const scheduled = reminders[key];
            const day = Number(b.due.slice(8, 10));
            return (
              <li key={key} className="flex flex-wrap items-center gap-4 py-4">
                <div className="flex size-14 shrink-0 flex-col items-center justify-center rounded-lg bg-secondary/60 text-center">
                  <span className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Day</span>
                  <span className="font-display text-lg font-extrabold leading-none">{day}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="font-medium capitalize">{prettyKind(b.kind)}</p>
                  <p className="text-xs text-muted-foreground">
                    {kindSubtitle(b.kind)} · due {b.due}
                  </p>
                </div>
                <p className="font-display text-lg font-bold tabular-nums">{money(b.amount, 2)}</p>
                <Button
                  size="sm"
                  variant={scheduled ? "secondary" : "default"}
                  onClick={() => setReminders((r) => ({ ...r, [key]: !r[key] }))}
                >
                  {scheduled ? "Reminder scheduled" : "Schedule reminder"}
                </Button>
              </li>
            );
          })}
        </ul>
        <div className="mt-6 rounded-xl border border-primary/30 bg-primary/5 px-4 py-3 text-xs text-muted-foreground">
          Scheduling creates a demo reminder in this browser only. It does not submit a bill payment.
        </div>
      </section>
    </div>
  );
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl border border-border/70 px-5 py-5">
      <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">{label}</p>
      <p className="mt-3 font-display text-3xl font-extrabold tabular-nums md:text-4xl">{value}</p>
    </div>
  );
}

function prettyKind(kind: string) {
  if (kind === "housing") return "Rent / housing";
  if (kind === "debt_payment") return "Debt payment";
  return kind.replaceAll("_", " ");
}

function kindSubtitle(kind: string) {
  if (kind === "housing") return "Housing — recurring monthly";
  if (kind === "utility") return "Utility — recurring monthly";
  if (kind === "subscription") return "Subscription — recurring monthly";
  if (kind === "insurance") return "Insurance — recurring monthly";
  if (kind === "debt_payment") return "Debt service — required payment";
  return "Recurring commitment";
}

// ------------------------------------------------------------------ Goals
function GoalsView({ customerId }: { customerId: string }) {
  const qc = useQueryClient();
  const goals = useFinanceQuery(["goals"], customerId, financeApi.goals);
  const [name, setName] = useState("Your next car");
  const [target, setTarget] = useState(8000);
  const [saved, setSaved] = useState(4000);
  const [monthly, setMonthly] = useState(400);

  const previewMonths = monthly > 0 ? Math.ceil(Math.max(target - saved, 0) / monthly) : null;
  const fasterMonths = monthly > 0 ? Math.ceil(Math.max(target - saved, 0) / (monthly + 200)) : null;
  const progress = target > 0 ? Math.min(100, (saved / target) * 100) : 0;

  const create = useMutation({
    mutationFn: () =>
      financeApi.createGoal({
        name,
        target_amount: target,
        starting_amount: saved,
        deadline: monthsFromNow(previewMonths ?? 12),
        planned_monthly_contribution: monthly,
      }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["finance", customerId, "goals"] }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => financeApi.deleteGoal(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["finance", customerId, "goals"] }),
  });

  return (
    <div className="space-y-8 pb-10">
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-2xl border border-border/70 px-6 py-7">
          <h3 className="font-display text-2xl font-extrabold">Make room for what&apos;s next</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Your goal. Your pace. A transparent timeline.
          </p>
          <form
            className="mt-6 space-y-4"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
          >
            <Field label="Goal name">
              <Input value={name} onChange={(e) => setName(e.target.value)} required />
            </Field>
            <Field label="Target amount ($)">
              <Input type="number" min={1} value={target} onChange={(e) => setTarget(Number(e.target.value))} required />
            </Field>
            <Field label="Already saved ($)">
              <Input type="number" min={0} value={saved} onChange={(e) => setSaved(Number(e.target.value))} />
            </Field>
            <Field label="Monthly contribution ($)">
              <Input type="number" min={1} value={monthly} onChange={(e) => setMonthly(Number(e.target.value))} required />
            </Field>
            <Button type="submit" className="w-full" size="lg" disabled={create.isPending}>
              Save my goal <ArrowRight />
            </Button>
            {create.error && <p className="text-sm text-destructive">{(create.error as Error).message}</p>}
          </form>
        </div>

        <div className="flex flex-col rounded-2xl border border-border/70 px-6 py-7">
          <div className="mx-auto flex size-14 items-center justify-center rounded-full border-2 border-primary/40">
            <Target className="size-6 text-primary" />
          </div>
          <p className="mt-6 text-center font-display text-7xl font-extrabold leading-none tabular-nums md:text-8xl">
            {previewMonths ?? "—"}
          </p>
          <p className="mt-2 text-center text-muted-foreground">months to your goal</p>

          <div className="mt-8">
            <div className="h-3 overflow-hidden rounded-full bg-secondary">
              <div className="h-full rounded-full bg-primary transition-all duration-500" style={{ width: `${progress}%` }} />
            </div>
            <p className="mt-2 text-sm text-muted-foreground">
              {money(saved, 0)} saved of {money(target, 0)}
            </p>
          </div>

          <div className="mt-auto space-y-3 border-t border-border/50 pt-6">
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">At your current pace</span>
              <span className="font-medium tabular-nums">{money(monthly, 0)}/mo</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-muted-foreground">Save $200 more each month</span>
              <span className="font-medium tabular-nums">{fasterMonths ?? "—"} months</span>
            </div>
          </div>
        </div>
      </div>

      {(goals.data?.goals.length ?? 0) > 0 && (
        <section>
          <h3 className="font-display text-xl font-extrabold">Saved goals</h3>
          <ul className="mt-4 divide-y divide-border/50 border-y border-border/50">
            {goals.data!.goals.map((g) => (
              <li key={g.goal_id} className="flex flex-wrap items-center justify-between gap-3 py-4">
                <div>
                  <p className="font-medium">{g.name}</p>
                  <p className="text-sm text-muted-foreground">
                    {money(g.current_amount || g.starting_amount, 0)} of {money(g.target_amount, 0)} by {g.deadline}
                  </p>
                </div>
                <Button size="sm" variant="ghost" onClick={() => remove.mutate(g.goal_id)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
      <div className="mt-1.5">{children}</div>
    </div>
  );
}

function monthsFromNow(n: number) {
  const d = new Date(2026, 9, 31); // align with demo as-of window end
  d.setMonth(d.getMonth() + Math.max(1, n));
  return d.toISOString().slice(0, 10);
}

// ------------------------------------------------------------------ Health / Loans
function HealthView({ customerId }: { customerId: string }) {
  const [extra, setExtra] = useState(100);
  const [price, setPrice] = useState(30000);
  const [down, setDown] = useState(5000);
  const [apr, setApr] = useState(8);
  const [term, setTerm] = useState(60);

  const xray = useFinanceQuery(["xray"], customerId, financeApi.xray);
  const accounts = useFinanceQuery(["accounts"], customerId, financeApi.accounts);
  const payoff = useFinanceQuery(["payoff", String(extra)], customerId, () => financeApi.payoff(extra));
  const purchase = useMutation({
    mutationFn: () =>
      financeApi.purchase({ price, down_payment: down, apr_pct: apr, term_months: term, save: false }),
  });

  useEffect(() => {
    purchase.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId]);

  const debts = useMemo(
    () =>
      (accounts.data?.accounts ?? []).filter((a) =>
        ["auto_loan", "personal_loan", "mortgage", "credit_card"].includes(a.account_type),
      ),
    [accounts.data],
  );

  if (xray.error || accounts.error) return <LoadError error={(xray.error || accounts.error) as Error} />;
  if (xray.isLoading) return <Skeleton className="h-72" />;

  const results = (payoff.data?.results ?? {}) as Record<string, unknown>;
  const alt = purchase.data?.scenario.results as Record<string, unknown> | undefined;
  const base = purchase.data?.baseline.results as Record<string, unknown> | undefined;

  return (
    <div className="space-y-10 pb-10">
      <section className="grid items-center gap-8 md:grid-cols-[auto_1fr]">
        <ScoreRing score={xray.data!.overall.score} band={xray.data!.overall.band} />
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.28em] text-muted-foreground">Financial X-Ray</p>
          <h3 className="mt-2 font-display text-3xl font-extrabold md:text-4xl">
            {xray.data!.overall.band} · {xray.data!.overall.score.toFixed(0)}
          </h3>
          <p className="mt-2 max-w-xl text-sm text-muted-foreground">{xray.data!.overall.disclaimer}</p>
        </div>
      </section>

      <section className="divide-y divide-border/50 border-y border-border/50">
        {xray.data!.indicators.map((ind) => (
          <div key={ind.id} className="grid gap-2 py-4 md:grid-cols-[12rem_1fr_auto] md:items-center">
            <div>
              <p className="font-medium">{ind.label}</p>
              <p className={`text-xs font-semibold uppercase ${statusTone(ind.status)}`}>{ind.status}</p>
            </div>
            <div>
              <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                <div className="h-full rounded-full bg-primary" style={{ width: `${ind.normalized}%` }} />
              </div>
              <p className="mt-2 text-sm text-muted-foreground">{ind.explanation}</p>
            </div>
            <p className="text-right font-display text-lg font-bold tabular-nums">
              {ind.unit.includes("fraction") ? pct(ind.raw) : ind.raw?.toFixed(1) ?? "—"}
            </p>
          </div>
        ))}
      </section>

      <section>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h3 className="font-display text-xl font-extrabold">Debt payoff</h3>
            <p className="text-sm text-muted-foreground">Snowball vs avalanche with extra monthly payment</p>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="extra" className="text-xs uppercase tracking-wider text-muted-foreground">
              Extra / mo
            </Label>
            <Input id="extra" type="number" className="w-28" value={extra} min={0} onChange={(e) => setExtra(Number(e.target.value) || 0)} />
          </div>
        </div>
        <div className="mt-4 divide-y divide-border/50 border-y border-border/50">
          {debts.map((d) => (
            <div key={d.account_id} className="flex justify-between gap-3 py-3">
              <div>
                <p className="font-medium">{d.name}</p>
                <p className="text-xs capitalize text-muted-foreground">
                  {d.account_type.replaceAll("_", " ")}
                  {d.apr_pct ? ` · ${Number(d.apr_pct).toFixed(2)}% APR` : ""}
                </p>
              </div>
              <p className="font-display text-xl font-bold tabular-nums">{money(d.balance, 2)}</p>
            </div>
          ))}
        </div>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {(["snowball", "avalanche"] as const).map((name) => {
            const s = results[name] as Record<string, unknown> | undefined;
            if (!s) return null;
            return (
              <div key={name} className="rounded-2xl border border-border/70 px-4 py-4">
                <p className="text-xs font-bold uppercase tracking-[0.2em] text-primary">{name}</p>
                <p className="mt-2 font-display text-2xl font-extrabold">{money(String(s.total_interest), 0)} interest</p>
                <p className="text-sm text-muted-foreground">{String(s.months)} months</p>
              </div>
            );
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-border/70 px-6 py-7">
        <h3 className="font-display text-xl font-extrabold">Car purchase what-if</h3>
        <p className="mt-1 text-sm text-muted-foreground">Workshop defaults: $30,000 · $5,000 down · 8% · 60 months</p>
        <form
          className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-5"
          onSubmit={(e) => {
            e.preventDefault();
            purchase.mutate();
          }}
        >
          {(
            [
              ["Price", price, setPrice],
              ["Down", down, setDown],
              ["APR %", apr, setApr],
              ["Term", term, setTerm],
            ] as const
          ).map(([label, value, set]) => (
            <div key={label}>
              <Label className="text-xs uppercase tracking-wider text-muted-foreground">{label}</Label>
              <Input type="number" className="mt-1" value={value} min={0} onChange={(e) => set(Number(e.target.value))} />
            </div>
          ))}
          <div className="flex items-end">
            <Button type="submit" className="w-full" disabled={purchase.isPending}>
              <Landmark /> Run
            </Button>
          </div>
        </form>
        {purchase.data && base && alt && (
          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <CompareMini title="Baseline" surplus={String(base.monthly_surplus)} liquid={String((base.projected_liquid_balance as Record<string, string>)["1y"])} />
            <CompareMini title="With purchase" surplus={String(alt.monthly_surplus)} liquid={String((alt.projected_liquid_balance as Record<string, string>)["1y"])} highlight />
          </div>
        )}
        {purchase.error && <p className="mt-3 text-sm text-destructive">{(purchase.error as Error).message}</p>}
      </section>
    </div>
  );
}

function CompareMini({
  title,
  surplus,
  liquid,
  highlight = false,
}: {
  title: string;
  surplus: string;
  liquid: string;
  highlight?: boolean;
}) {
  return (
    <div className={`rounded-xl border px-4 py-4 ${highlight ? "border-primary/40 bg-primary/5" : "border-border/60"}`}>
      <p className="text-xs font-bold uppercase tracking-wider text-primary">{title}</p>
      <p className="mt-2 text-sm text-muted-foreground">Monthly surplus</p>
      <p className="font-display text-2xl font-extrabold tabular-nums">{money(surplus, 0)}</p>
      <p className="mt-3 text-sm text-muted-foreground">Liquid in 1 year</p>
      <p className="font-display text-lg font-bold tabular-nums">{money(liquid, 0)}</p>
    </div>
  );
}

function ScoreRing({ score, band }: { score: number; band: string }) {
  const r = 54;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(Math.max(score, 0), 100) / 100);
  return (
    <div className="relative mx-auto size-36">
      <svg viewBox="0 0 140 140" className="size-full -rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" className="text-secondary" stroke="currentColor" strokeWidth="10" />
        <circle
          cx="70"
          cy="70"
          r={r}
          fill="none"
          className="text-primary"
          stroke="currentColor"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={offset}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-3xl font-extrabold tabular-nums">{score.toFixed(0)}</span>
        <span className="text-[10px] font-bold uppercase tracking-wider text-primary">{band}</span>
      </div>
    </div>
  );
}
