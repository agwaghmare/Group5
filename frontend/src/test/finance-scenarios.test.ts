import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Snapshot } from "@/lib/finance-api";
import { savingsTransfer, trimmedBills, savingsGoal, loanPlan, paySchedule, projectCash } from "@/lib/finance-scenarios";

const csv = readFileSync(resolve(process.cwd(), "../data/personal_finance_tracker_dataset.csv"), "utf8").trim().split(/\r?\n/);
const columns = csv[0]!.split(",");
const latest = new Map<string, Snapshot>();
for (const line of csv.slice(1)) {
  const fields = line.split(",");
  if (fields.length !== columns.length) throw new Error("Unexpected CSV row shape");
  const row = Object.fromEntries(columns.map((key, index) => [key, fields[index]])) as unknown as Snapshot;
  const key = String(row.user_id);
  if (!latest.has(key) || latest.get(key)!.date < row.date) latest.set(key, Object.freeze(row));
}
const customers = [...latest.values()];
const sample = { ...customers[0]!, date: "2024-06-01", checking_balance: 11416, savings_balance: 14557,
  available_balance: 11354, projected_balance_30d: 14313 } as Snapshot;
const close = (actual: number, expected: number) => {
  if (Math.abs(actual - expected) > 0.021) throw new Error(`${actual} differs from ${expected}`);
};

describe("Finance scenario stress tests", () => {
  it("reproduces the reported $650 and $1,225 transfers consistently", () => {
    const first = savingsTransfer(sample, 650);
    expect(first).toMatchObject({ checking: 10766, savings: 15207, available: 10704, projected30d: 13663 });
    const second = savingsTransfer(sample, 1225);
    expect(second).toMatchObject({ checking: 10191, savings: 15782, available: 10129, projected30d: 13088 });
    expect(second.points[0]).toMatchObject({ Checking: second.checking, Savings: second.savings });
    expect(sample.checking_balance).toBe(11416);
  });

  it("conserves cash across every savings-slider position for all 500 customers", () => {
    expect(customers).toHaveLength(500);
    for (const row of customers) {
      for (let extra = 0; extra <= 2000; extra += 25) {
        const plan = savingsTransfer(row, extra);
        close(plan.checking + plan.savings, Number(row.checking_balance) + Number(row.savings_balance));
        close(Number(row.available_balance) - plan.available, plan.transfer);
        close(plan.checking - plan.available, Number(row.checking_balance) - Number(row.available_balance));
        for (const point of plan.points) {
          close(point.Checking + point.Savings, Number(row.checking_balance) + Number(row.savings_balance));
          if (Number(row.checking_balance) >= 0 && point.Checking < -0.01) throw new Error("Transfer overdraws checking");
        }
      }
    }
  });

  it("caps savings transfers when available funds are exhausted", () => {
    const row = { ...sample, checking_balance: 100, available_balance: 75 };
    const plan = savingsTransfer(row, 2000);
    expect(plan).toMatchObject({ transfer: 75, checking: 25, available: 0 });
    expect(plan.points.at(-1)!.Checking).toBe(25);
  });

  it("keeps fixed debt and every bill component reconciled at trim boundaries", () => {
    for (const row of customers) {
      const bills = Number(row.recurring_bill_total);
      const subs = Number(row.subscription_cost_monthly);
      const debt = Number(row.minimum_debt_payment);
      for (const cut of [0, 25, 650, 1225, 2000, bills, bills + subs, 1e9]) {
        const plan = trimmedBills(row, cut);
        close(plan.committed, plan.bills + plan.subscriptions + debt);
        close(plan.remaining + plan.committed, Number(row.monthly_income));
        close(plan.debt, debt);
        if (plan.bills < -0.01 || plan.subscriptions < -0.01 || plan.committed < debt - 0.01) throw new Error("Trims reduced fixed debt");
      }
    }
  });

  it("computes attainable savings targets over the entire target slider", () => {
    for (const row of customers) {
      for (let target = 1; target <= 12; target++) {
        let previous = Infinity;
        for (const monthly of [0, 25, 650, 1225, 2000]) {
          const plan = savingsGoal(row, target, monthly);
          if (plan.dollarsShort === 0 && plan.monthsToTarget !== 0) throw new Error("Already-met goal needs no wait");
          if (plan.monthsToTarget !== null) {
            if (plan.monthsToTarget > previous) throw new Error("Higher savings increased wait");
            previous = plan.monthsToTarget;
            if (plan.dollarsShort > 0) {
              if (plan.monthsToTarget * monthly < plan.dollarsShort || (plan.monthsToTarget - 1) * monthly >= plan.dollarsShort) throw new Error("Incorrect goal horizon");
            }
          }
        }
      }
    }
    expect(savingsGoal({ ...sample, emergency_fund_months: 8 }, 6, 0).monthsToTarget).toBe(0);
    const fallback = savingsGoal({ ...sample, savings_balance: 0, emergency_fund_months: 0,
      recurring_bill_total: 1000, subscription_cost_monthly: 100, minimum_debt_payment: 100 }, 6, 200);
    expect(fallback).toMatchObject({ monthlyBurn: 1200, targetDollars: 7200, monthsToTarget: 36 });
  });

  it("amortizes loans across zero rates, large balances, long terms and extra payments", () => {
    for (const principal of [0, 500, 1000, 3800, 15000, 50000, 250000, 1500000]) {
      for (const apr of [0, 1e-10, 0.5, 12, 24, 50]) {
        for (const term of [1, 12, 48, 84, 360]) {
          let previousInterest = Infinity;
          for (const extra of [0, 25, 650, 1000]) {
            const plan = loanPlan(principal, apr, term, extra, 5000, 2000);
            if (plan.payoff === null || plan.payoff > term + 1) throw new Error("Amortizing loan did not pay off");
            if (!Number.isFinite(plan.interest) || plan.interest < 0 || plan.interest > previousInterest + 0.01) throw new Error("Invalid interest or extra-payment direction");
            previousInterest = plan.interest;
            close(plan.surplus + plan.totalPayment + 2000, 5000);
            let previousBalance = Infinity;
            for (const point of plan.points) {
              if (point.Balance < 0 || point.Balance > previousBalance + 0.01) throw new Error("Loan balance rose");
              previousBalance = point.Balance;
            }
            expect(plan.points.at(-1)!.Balance).toBe(0);
          }
        }
      }
    }
    expect(loanPlan(12000, 10, 36, 0, 5000, 2000).payment).toBeCloseTo(387.21, 2);
    expect(loanPlan(12000, 0, 12, 0, 0, 0)).toMatchObject({ payment: 1000, interest: 0, payoff: 12, dti: null });
  });

  it("keeps the baseline fixed and reports shocks on their actual first day", () => {
    expect(paySchedule("biweekly")).toEqual({ interval: 14, paymentsPerYear: 26 });
    expect(paySchedule("semi-monthly")).toEqual({ interval: 15, paymentsPerYear: 24 });
    for (const row of customers) {
      for (const days of [14, 30, 90, 120]) {
        const normal = projectCash(row, { days, incomeCut: 0, livingUp: 0, emergency: 0, delay: 0 });
        for (const point of normal.points) close(point.Scenario, point.Baseline);
        for (const shock of [
          { incomeCut: 80, livingUp: 0, emergency: 0, delay: 0 },
          { incomeCut: 0, livingUp: 80, emergency: 0, delay: 0 },
          { incomeCut: 0, livingUp: 0, emergency: 10000, delay: 0 },
          { incomeCut: 80, livingUp: 80, emergency: 10000, delay: 30 },
        ]) {
          const stressed = projectCash(row, { days, ...shock });
          if (stressed.ending > normal.ending + 0.01 || stressed.lowest > normal.lowest + 0.01) throw new Error("Adverse shock improved finances");
          for (let index = 0; index < stressed.points.length; index++) close(stressed.points[index]!.Baseline, normal.points[index]!.Baseline);
        }
      }
    }
    expect(projectCash({ ...sample, available_balance: 50 }, { days: 30, incomeCut: 0, livingUp: 0, emergency: 100, delay: 0 }).shortfall).toBe("6/1");
  });
});
