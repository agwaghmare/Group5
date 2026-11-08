import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FinanceSection } from "@/components/finance/finance-section";

const state = vi.hoisted(() => ({ snapshot: {
  user_id: 1000, date: "2024-06-01", monthly_income: 5000, pay_frequency: "biweekly",
  checking_balance: 11416, savings_balance: 14557, available_balance: 11354,
  projected_balance_30d: 14313, portfolio_value: 9383, home_equity: 0,
  recurring_bill_total: 1000, subscription_cost_monthly: 200, minimum_debt_payment: 100,
  emergency_fund_months: 5.73, monthly_savings_contribution: 500, savings_apy: 4,
  total_debt_balance: 3800, weighted_avg_apr: 12.5, remaining_loan_term_months: 60,
  bill_payment_delay_count: 0, overdraft_count_90d: 0,
} }));
vi.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: { customer_id: "1000", snapshots: [state.snapshot] } }) }));
vi.mock("@/lib/customer-session", () => ({
  useCustomerSession: () => ({ email: "test@example.test", token: "session", isStaff: false }),
  readCustomerSession: () => null,
}));
vi.mock("@/components/ui/slider", () => ({ Slider: (props: {
  value: number[]; min: number; max: number; step: number; disabled: boolean;
  "aria-label": string; onValueChange: (values: number[]) => void;
}) => <input type="range" aria-label={props["aria-label"]} value={props.value[0]}
  min={props.min} max={props.max} step={props.step} disabled={props.disabled}
  onChange={(event) => props.onValueChange([Number(event.target.value)])} /> }));
vi.mock("recharts", () => {
  const chart = ({ data }: { data: unknown }) => <pre data-testid="chart-data">{JSON.stringify(data)}</pre>;
  return { ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
    LineChart: chart, AreaChart: chart, Line: () => null, Area: () => null,
    CartesianGrid: () => null, XAxis: () => null, YAxis: () => null, Tooltip: () => null };
});
const recordedSnapshot = { ...state.snapshot };
afterEach(() => { cleanup(); Object.assign(state.snapshot, recordedSnapshot); });
const change = (label: string, value: number) => fireEvent.change(screen.getByRole("slider", { name: label }), { target: { value: String(value) } });
const card = (label: string) => screen.getByText(label, { selector: "p" }).parentElement!.textContent;
const chart = () => JSON.parse(screen.getByTestId("chart-data").textContent ?? "[]") as Record<string, number | string>[];

describe("Finance slider wiring", () => {
  it("updates the headline, Checking, Savings and chart together for the reported values", () => {
    render(<FinanceSection view="money" onViewChange={vi.fn()} />);
    change("Extra monthly savings", 650);
    expect(screen.getByText("$10,704")).toBeInTheDocument();
    expect(card("Checking")).toContain("$10,766");
    expect(card("Savings")).toContain("$15,207");
    expect(chart()[1]).toMatchObject({ Checking: 10766, Savings: 15207 });
    change("Extra monthly savings", 1225);
    expect(screen.getByText("$10,129")).toBeInTheDocument();
    expect(card("Checking")).toContain("$10,191");
    expect(card("Savings")).toContain("$15,782");
    expect(card("Portfolio")).toContain("$9,383");
    expect(card("Home equity")).toContain("$0");
    expect(chart()[0]).toMatchObject({ Checking: 11416, Savings: 14557 });
    expect(chart()[1]).toMatchObject({ Checking: 10191, Savings: 15782 });
    expect(state.snapshot.checking_balance).toBe(11416);
    change("Extra monthly savings", 0);
    expect(card("Checking")).toContain("$11,416");
    expect(card("Savings")).toContain("$14,557");
  });

  it("reconciles trimmed bills and subscriptions without changing history or debt", () => {
    render(<FinanceSection view="bills" onViewChange={vi.fn()} />);
    change("Bills you could trim", 100);
    expect(card("Recurring bills")).toContain("$1,000");
    expect(card("Subscriptions")).toContain("$100");
    expect(chart()[1]).toMatchObject({ Bills: 1000, Subscriptions: 100, Debt: 100 });
    change("Bills you could trim", 200);
    expect(card("Recurring bills")).toContain("$1,000");
    expect(card("Subscriptions")).toContain("$0");
    change("Bills you could trim", 1100);
    expect(card("Recurring bills")).toContain("$100");
    expect(card("Subscriptions")).toContain("$0");
    expect(card("Minimum debt")).toContain("$100");
    expect(chart()[0]).toMatchObject({ Bills: 1000, Subscriptions: 200, Debt: 100 });
    expect(chart()[1]).toMatchObject({ Bills: 100, Subscriptions: 0, Debt: 100 });
  });

  it("updates savings projections and recognizes an already-met goal at zero contribution", () => {
    render(<FinanceSection view="goals" onViewChange={vi.fn()} />);
    change("Monthly contribution", 650);
    expect(card("Savings after one month")).toContain("$15,207");
    change("Target coverage", 3);
    change("Monthly contribution", 0);
    expect(screen.getByText("This snapshot already meets that coverage.")).toBeInTheDocument();
    expect(card("Months to target")).toContain("0");
  });

  it("updates total loan payments and payoff when extra payments change", () => {
    render(<FinanceSection view="health" onViewChange={vi.fn()} />);
    const before = card("Total interest");
    change("Extra monthly payment", 650);
    expect(card("Total interest")).not.toBe(before);
    expect(card("Payoff")).not.toContain("60 mo");
    expect(screen.getByRole("slider", { name: "Loan amount" })).toHaveValue("3800");
  });

  it("changes only the scenario in What If and restores it with Normal", () => {
    render(<FinanceSection view="whatif" onViewChange={vi.fn()} />);
    const original = chart();
    change("Income reduction", 80);
    change("One-time emergency", 10000);
    const changed = chart();
    expect(changed.map((point) => point["Baseline"])).toEqual(original.map((point) => point["Baseline"]));
    expect(changed.map((point) => point["Scenario"])).not.toEqual(original.map((point) => point["Scenario"]));
    fireEvent.click(screen.getByRole("button", { name: "Normal" }));
    expect(chart()).toEqual(original);
  });

  it("explains Monte Carlo and collapses the simulated range when variation is zero", () => {
    render(<FinanceSection view="whatif" onViewChange={vi.fn()} />);
    expect(screen.getByRole("region", { name: "Monte Carlo simulation" })).toHaveTextContent("1,000 possible cash-flow paths");
    expect(screen.getByText("Runs with a cash shortfall")).toBeInTheDocument();
    expect(chart().at(-1)!["Lower"]).toBeLessThan(Number(chart().at(-1)!["Upper"]));
    change("Income variation", 0); change("Spending variation", 0);
    for (const point of chart()) {
      expect(point["Lower"]).toBe(point["Scenario"]);
      expect(point["Median"]).toBe(point["Scenario"]);
      expect(point["Upper"]).toBe(point["Scenario"]);
    }
    expect(screen.getByText(/not a measured probability/)).toBeInTheDocument();
  });

  it("keeps small debts, short remaining terms and higher recorded APRs", () => {
    Object.assign(state.snapshot, { total_debt_balance: 831.43, weighted_avg_apr: 31.7, remaining_loan_term_months: 7 });
    render(<FinanceSection view="health" onViewChange={vi.fn()} />);
    expect(screen.getByRole("slider", { name: "Loan amount" })).toHaveValue("831.43");
    expect(screen.getByRole("slider", { name: "APR" })).toHaveValue("31.7");
    expect(screen.getByRole("slider", { name: "Loan months" })).toHaveValue("7");
  });

  it("does not invent a loan for a customer with no recorded debt", () => {
    state.snapshot.total_debt_balance = 0;
    render(<FinanceSection view="health" onViewChange={vi.fn()} />);
    expect(screen.getByRole("slider", { name: "Loan amount" })).toHaveValue("0");
    expect(card("Total interest")).toContain("$0");
    expect(card("Payoff")).toContain("0 mo");
  });

  it("resets the scenario when a different snapshot is loaded", () => {
    const { rerender } = render(<FinanceSection view="money" onViewChange={vi.fn()} />);
    change("Extra monthly savings", 650);
    Object.assign(state.snapshot, { date: "2024-07-01", checking_balance: 12000 });
    rerender(<FinanceSection view="money" onViewChange={vi.fn()} />);
    expect(screen.getByRole("slider", { name: "Extra monthly savings" })).toHaveValue("0");
    expect(card("Checking")).toContain("$12,000");
  });
});
