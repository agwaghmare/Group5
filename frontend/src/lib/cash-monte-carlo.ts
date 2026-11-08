import type { Snapshot } from "./finance-api";
import { paySchedule, projectCash } from "./finance-scenarios";

type Scenario = Parameters<typeof projectCash>[1];
const numeric = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : 0;
const positive = (value: unknown) => Math.max(0, numeric(value));
const clamp = (value: number, low: number, high: number) => Math.max(low, Math.min(high, numeric(value)));
const cents = (value: number) => Math.round(value * 100) / 100;

export function recordedIncomeVariation(latest: Snapshot) {
  const value = latest.income_volatility_3m;
  return value === null || value === undefined || value === "" || !Number.isFinite(Number(value))
    ? .1 : clamp(Number(value), 0, 1);
}

function randomSource(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6D2B79F5) | 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function simulateCash(latest: Snapshot, scenario: Scenario, options: {
  runs?: number; seed?: number; incomeVariation?: number; spendingVariation?: number;
} = {}) {
  const runs = Math.round(clamp(options.runs ?? 1000, 1, 5000));
  const days = Math.round(clamp(scenario.days, 0, 365));
  const sampleDays = Array.from({ length: 16 }, (_, index) => Math.round(index / 15 * days));
  const samples: number[][] = sampleDays.map(() => []);
  const incomeVariation = clamp(options.incomeVariation ?? recordedIncomeVariation(latest), 0, 1);
  const spendingVariation = clamp(options.spendingVariation ?? .1, 0, 1);
  const incomeSigma = Math.sqrt(Math.log1p(incomeVariation ** 2));
  const spendingSigma = Math.sqrt(Math.log1p(spendingVariation ** 2));
  let seed = 2166136261;
  for (const char of `${latest.user_id}:${latest.date}`) seed = Math.imul(seed ^ char.charCodeAt(0), 16777619);
  if (options.seed !== undefined) seed = numeric(options.seed) >>> 0;
  const { interval, paymentsPerYear } = paySchedule(latest.pay_frequency);
  const paycheck = positive(latest.monthly_income) * 12 / paymentsPerYear * (1 - clamp(scenario.incomeCut, 0, 100) / 100);
  const dailyLiving = (positive(latest.recurring_bill_total) + positive(latest.subscription_cost_monthly))
    * (1 + clamp(scenario.livingUp, 0, 100) / 100) / 30;
  const dailyDebt = positive(latest.minimum_debt_payment) / 30;
  const delay = Math.round(positive(scenario.delay));
  let shortfallRuns = 0;
  for (let run = 0; run < runs; run++) {
    const random = randomSource(seed + Math.imul(run + 1, 0x9E3779B9));
    // Mean-one lognormal factors keep costs and income nonnegative, without
    // shifting their expected levels. sigma = sqrt(log(1 + coefficientOfVariation^2)).
    // Reference: NIST e-Handbook, Lognormal Distribution, section 1.3.6.6.9.
    const factor = (sigma: number) => {
      const normal = Math.sqrt(-2 * Math.log(Math.max(random(), Number.MIN_VALUE))) * Math.cos(2 * Math.PI * random());
      return Math.exp(sigma * normal - sigma * sigma / 2);
    };
    let balance = numeric(latest.available_balance) - positive(scenario.emergency);
    let shortfall = balance < 0;
    let sample = 0;
    const capture = (day: number) => {
      while (sample < sampleDays.length && sampleDays[sample] === day) samples[sample++]!.push(balance);
    };
    capture(0);
    let incomeFactor = 1, spendingFactor = 1;
    for (let day = 1; day <= days; day++) {
      // Refresh independent income and spending levels in each thirty-day block.
      // Reuse the same random draws across slider changes for stable comparisons.
      if ((day - 1) % 30 === 0) { incomeFactor = factor(incomeSigma); spendingFactor = factor(spendingSigma); }
      balance -= dailyLiving * spendingFactor + dailyDebt;
      if (day > delay && (day - delay) % interval === 0) balance += paycheck * incomeFactor;
      if (balance < 0) shortfall = true;
      capture(day);
    }
    if (shortfall) shortfallRuns++;
  }
  const percentile = (sorted: number[], fraction: number) => {
    const index = (sorted.length - 1) * fraction;
    const lower = Math.floor(index), upper = Math.ceil(index);
    return cents(sorted[lower]! + (sorted[upper]! - sorted[lower]!) * (index - lower));
  };
  const points = samples.map((values) => {
    values.sort((a, b) => a - b);
    return { Lower: percentile(values, .1), Median: percentile(values, .5), Upper: percentile(values, .9) };
  });
  const last = samples.at(-1)!;
  return { runs, incomeVariation, spendingVariation, shortfallRuns, shortfallRate: shortfallRuns / runs, points,
    ending: { ...points.at(-1)!, mean: cents(last.reduce((sum, value) => sum + value, 0) / runs) } };
}
