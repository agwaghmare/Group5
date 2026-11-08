import type { Snapshot } from "./finance-api";

const number = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};
const positive = (value: unknown) => Math.max(0, number(value));
const cents = (value: number) => Math.round(value * 100) / 100;
const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, number(value)));

export function savingsTransfer(latest: Snapshot, requested: number) {
  const checking = number(latest.checking_balance);
  const available = number(latest.available_balance);
  const savings = number(latest.savings_balance);
  const transferable = Math.max(0, Math.min(checking, available));
  const transfer = cents(clamp(requested, 0, transferable));
  return {
    transfer, transferable,
    checking: cents(checking - transfer), savings: cents(savings + transfer),
    available: cents(available - transfer),
    projected30d: cents(number(latest.projected_balance_30d) - transfer),
    points: Array.from({ length: 6 }, (_, index) => {
      const moved = Math.min(transfer * (index + 1), transferable);
      return { label: `+${index + 1} mo`, Checking: cents(checking - moved), Savings: cents(savings + moved) };
    }),
  };
}

export function trimmedBills(latest: Snapshot, requested: number) {
  const bills = positive(latest.recurring_bill_total);
  const subscriptions = positive(latest.subscription_cost_monthly);
  const debt = positive(latest.minimum_debt_payment);
  const cut = cents(clamp(requested, 0, bills + subscriptions));
  const adjustedSubscriptions = cents(Math.max(0, subscriptions - cut));
  const adjustedBills = cents(Math.max(0, bills - Math.max(0, cut - subscriptions)));
  const committed = cents(adjustedBills + adjustedSubscriptions + debt);
  return { cut, bills: adjustedBills, subscriptions: adjustedSubscriptions, debt, committed,
    remaining: cents(number(latest.monthly_income) - committed), maximumCut: bills + subscriptions };
}

export function savingsGoal(latest: Snapshot, target: number, contribution: number) {
  const savings = positive(latest.savings_balance);
  const coverage = positive(latest.emergency_fund_months);
  const monthlyBurn = coverage > 0 ? savings / coverage
    : positive(latest.recurring_bill_total) + positive(latest.subscription_cost_monthly) + positive(latest.minimum_debt_payment);
  const targetDollars = cents(monthlyBurn * positive(target));
  const dollarsShort = cents(Math.max(0, targetDollars - savings));
  const monthly = positive(contribution);
  const monthsToTarget = dollarsShort === 0 ? 0 : monthly > 0 ? Math.ceil(dollarsShort / monthly) : null;
  return { savings, monthlyBurn, targetDollars, dollarsShort, monthly, monthsToTarget,
    basisAvailable: monthlyBurn > 0, afterOneMonth: cents(savings + monthly) };
}

export function paySchedule(frequency: string) {
  const value = String(frequency).toLowerCase().replace(/[\s_-]/g, "");
  if (value.includes("semi")) return { interval: 15, paymentsPerYear: 24 };
  if (value.includes("biweek") || value.includes("fortnight")) return { interval: 14, paymentsPerYear: 26 };
  if (value.includes("week")) return { interval: 7, paymentsPerYear: 52 };
  return { interval: 30, paymentsPerYear: 12 };
}

export function projectCash(latest: Snapshot, input: {
  days: number; incomeCut: number; livingUp: number; emergency: number; delay: number;
}) {
  const days = Math.round(clamp(input.days, 0, 365));
  const start = number(latest.available_balance);
  const monthlyIncome = positive(latest.monthly_income);
  const monthlyLiving = positive(latest.recurring_bill_total) + positive(latest.subscription_cost_monthly);
  const monthlyDebt = positive(latest.minimum_debt_payment);
  const { interval, paymentsPerYear } = paySchedule(latest.pay_frequency);
  const origin = new Date(`${latest.date}T00:00:00Z`);
  const labelFor = (day: number) => {
    const when = new Date(origin);
    when.setUTCDate(when.getUTCDate() + day);
    return `${when.getUTCMonth() + 1}/${when.getUTCDate()}`;
  };
  const walk = (shock: boolean) => {
    let balance = start - (shock ? positive(input.emergency) : 0);
    let lowest = balance;
    let shortfall: string | null = balance < 0 ? labelFor(0) : null;
    const points = [balance];
    const daily = (monthlyLiving * (shock ? 1 + clamp(input.livingUp, 0, 100) / 100 : 1) + monthlyDebt) / 30;
    const paycheck = monthlyIncome * 12 / paymentsPerYear * (shock ? 1 - clamp(input.incomeCut, 0, 100) / 100 : 1);
    const delay = shock ? Math.round(positive(input.delay)) : 0;
    for (let day = 1; day <= days; day += 1) {
      balance -= daily;
      if (day > delay && (day - delay) % interval === 0) balance += paycheck;
      lowest = Math.min(lowest, balance);
      if (balance < 0 && shortfall === null) shortfall = labelFor(day);
      points.push(balance);
    }
    return { points, lowest, ending: balance, shortfall };
  };
  const scenario = walk(true);
  const baseline = walk(false);
  return {
    lowest: scenario.lowest, ending: scenario.ending, shortfall: scenario.shortfall,
    points: Array.from({ length: 16 }, (_, index) => {
      const day = Math.round(index / 15 * days);
      return { label: labelFor(day), Scenario: cents(scenario.points[day]!), Baseline: cents(baseline.points[day]!) };
    }),
  };
}

export function loanPlan(principal: number, apr: number, term: number, extra: number, income: number, living: number) {
  principal = positive(principal);
  term = Math.max(1, Math.round(positive(term)));
  const rate = positive(apr) / 100 / 12;
  extra = positive(extra);
  const payment = rate === 0 ? principal / term : principal * rate / -Math.expm1(-term * Math.log1p(rate));
  let balance = principal;
  let interest = 0;
  let payoff: number | null = principal === 0 ? 0 : null;
  const series = [balance];
  for (let month = 1; month <= term + 1 && balance > 0; month += 1) {
    const charge = balance * rate;
    const due = payment + extra;
    if (due <= charge && rate > 0) break;
    const paid = Math.min(balance + charge, due);
    interest += charge;
    balance = Math.max(0, balance + charge - paid);
    if (balance < 0.000001) { balance = 0; payoff = month; }
    series.push(balance);
  }
  const totalPayment = principal > 0 ? Math.min(principal * (1 + rate), payment + extra) : 0;
  return {
    payment, totalPayment, interest, payoff,
    dti: income > 0 ? payment / income : null,
    surplus: number(income) - positive(living) - totalPayment,
    points: Array.from({ length: 25 }, (_, index) => {
      const month = Math.round(index / 24 * term);
      return { label: String(month), Balance: cents(series[Math.min(month, series.length - 1)] ?? 0) };
    }),
  };
}
