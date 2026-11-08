import { describe, expect, it } from "vitest";
import type { Snapshot } from "@/lib/finance-api";
import { projectCash } from "@/lib/finance-scenarios";
import { recordedIncomeVariation, simulateCash } from "@/lib/cash-monte-carlo";

const snapshot = { user_id: 1000, date: "2024-06-01", available_balance: 10000,
  monthly_income: 3000, recurring_bill_total: 1000, subscription_cost_monthly: 200,
  minimum_debt_payment: 100, pay_frequency: "monthly", income_volatility_3m: .2 } as Snapshot;
const normal = { days: 30, incomeCut: 0, livingUp: 0, emergency: 0, delay: 0 };

describe("Monte Carlo cash-flow simulations", () => {
  it("collapses to the fixed forecast with no uncertainty, including different pay schedules and horizons", () => {
    for (const pay_frequency of ["weekly", "biweekly", "semi-monthly", "monthly"]) for (const days of [0, 1, 14, 30, 90, 120]) {
      const row = { ...snapshot, pay_frequency };
      const input = { ...normal, days, incomeCut: 30, livingUp: 20, emergency: 500, delay: 7 };
      const fixed = projectCash(row, input);
      const result = simulateCash(row, input, { runs: 10, incomeVariation: 0, spendingVariation: 0 });
      expect(result.ending.Median).toBeCloseTo(fixed.ending, 2);
      expect(result.shortfallRate).toBe(fixed.shortfall === null ? 0 : 1);
      result.points.forEach((point, index) => expect(point).toEqual({
        Lower: fixed.points[index]!.Scenario, Median: fixed.points[index]!.Scenario, Upper: fixed.points[index]!.Scenario,
      }));
    }
  });

  it("is reproducible and generates ordered percentiles with the expected mean", () => {
    const options = { runs: 5000, seed: 12345, incomeVariation: .25, spendingVariation: .2 };
    const result = simulateCash(snapshot, normal, options);
    expect(simulateCash(snapshot, normal, options)).toEqual(result);
    const different = simulateCash(snapshot, normal, { ...options, seed: 54321 });
    expect(result.ending.Median).not.toBe(different.ending.Median);
    expect(result.ending.Upper - result.ending.Lower).toBeGreaterThan(1000);
    expect(Math.abs(result.ending.mean - projectCash(snapshot, normal).ending)).toBeLessThan(50);
    for (const point of result.points) {
      expect(point.Lower).toBeLessThanOrEqual(point.Median);
      expect(point.Median).toBeLessThanOrEqual(point.Upper);
      expect(Object.values(point).every(Number.isFinite)).toBe(true);
    }
    expect(result.points[0]).toEqual({ Lower: 10000, Median: 10000, Upper: 10000 });
  });

  it("counts a shortfall during the period even if ending cash recovers", () => {
    const result = simulateCash({ ...snapshot, available_balance: 100 }, normal, { incomeVariation: 0, spendingVariation: 0 });
    expect(result.ending.Lower).toBeGreaterThan(0);
    expect(result.shortfallRuns).toBe(result.runs);
    expect(simulateCash({ ...snapshot, available_balance: -1 }, { ...normal, days: 0 }).shortfallRate).toBe(1);
  });

  it("keeps shocks unfavorable with the same random draws and leaves the input unchanged", () => {
    const row = Object.freeze({ ...snapshot, available_balance: 1000 });
    const original = { ...row };
    const baseline = simulateCash(row, { ...normal, days: 120 });
    const stressed = simulateCash(row, { ...normal, days: 120, incomeCut: 70, livingUp: 60, emergency: 1500 });
    expect(stressed.shortfallRate).toBeGreaterThanOrEqual(baseline.shortfallRate);
    stressed.points.forEach((point, index) => {
      expect(point.Lower).toBeLessThanOrEqual(baseline.points[index]!.Lower);
      expect(point.Median).toBeLessThanOrEqual(baseline.points[index]!.Median);
      expect(point.Upper).toBeLessThanOrEqual(baseline.points[index]!.Upper);
    });
    expect(row).toEqual(original);
    expect(recordedIncomeVariation({ ...snapshot, income_volatility_3m: "" })).toBe(.1);
    expect(recordedIncomeVariation({ ...snapshot, income_volatility_3m: 0 })).toBe(0);
  });
});
