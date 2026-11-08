import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InvestmentWorkspace } from "@/components/finance/customer-investments";
import { editableInvestmentProfile, investmentProjection, previewCustomerPortfolio, type CustomerPortfolio } from "@/lib/customer-portfolio";

vi.mock("@/lib/customer-portfolio", async (original) => ({
  ...await original<typeof import("@/lib/customer-portfolio")>(), previewCustomerPortfolio: vi.fn(),
}));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  LineChart: () => <p>Investment chart</p>, XAxis: () => null, YAxis: () => null, Tooltip: () => null, Line: () => null,
}));
const portfolio: CustomerPortfolio = {
  client_id: 1000, value_cents: 100000, as_of: "2024-06-01", disclaimer: "Synthetic portfolio",
  allocations: { stocks: .5, bonds: .35, foreign: .15 }, holdings: [],
  profile: { goal: "Long-term investing", horizon_months: 120, tolerance: 3, liquidity_need_cents: 0, target_return: .05 },
  assessment: { allocations: { stocks: .5, bonds: .35, foreign: .15 }, risk_capacity: "moderate", risk_budget: .12,
    flags: [], binding_limits: ["financial_capacity"], return_history: [],
    metrics: { annualized_return: .04, volatility: .08, max_drawdown: -.1, total_return: .2 } },
};
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const change = (label: string, value: number) => fireEvent.change(screen.getByRole("slider", { name: label }), { target: { value: String(value) } });

describe("Customer investment views", () => {
  it("sends only editable profile fields, excluding server metadata", () => {
    const source = { ...portfolio.profile, questionnaire: { source: "Synthetic" }, synthetic: true };
    expect(editableInvestmentProfile(source)).toEqual(portfolio.profile);
    expect(editableInvestmentProfile(source)).not.toHaveProperty("questionnaire");
  });
  it("reconciles projection amounts over the entire return/horizon slider range", () => {
    for (const rate of [-.2, 0, .05, .2]) for (const months of [1, 12, 120, 600]) {
      const plan = investmentProjection(1000, 100, rate, months);
      expect(plan.contributed).toBe(1000 + months * 100);
      expect(Number.isFinite(plan.ending)).toBe(true);
      if (rate === 0) expect(plan.ending).toBe(plan.contributed);
      if (rate > 0) expect(plan.ending).toBeGreaterThan(plan.contributed);
      if (rate < 0) expect(plan.ending).toBeLessThan(plan.contributed);
    }
  });

  it("updates overview amounts, allocation totals and profile previews", async () => {
    vi.mocked(previewCustomerPortfolio).mockResolvedValue({ assessment: portfolio.assessment, preview_only: true });
    render(<InvestmentWorkspace portfolio={portfolio} />);
    change("Assumed annual return", 0); change("Monthly investment contribution", 100); change("Investment horizon (months)", 12);
    expect(screen.getByText("Scenario ending value").parentElement).toHaveTextContent("$2,200");
    fireEvent.click(screen.getByRole("button", { name: "Risk & Return" }));
    change("Domestic stocks", 90);
    expect(screen.getByRole("slider", { name: "Foreign equities" })).toHaveValue("10");
    await waitFor(() => expect(previewCustomerPortfolio).toHaveBeenLastCalledWith(expect.objectContaining({
      allocations: { stocks: .9, bonds: 0, foreign: .1 },
    }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    change("Risk tolerance", 1);
    await waitFor(() => expect(previewCustomerPortfolio).toHaveBeenLastCalledWith(expect.objectContaining({
      profile: expect.objectContaining({ tolerance: 1 }),
    }), expect.any(AbortSignal)));
    fireEvent.click(screen.getByRole("button", { name: "Reset what-if" }));
    expect(screen.getByRole("slider", { name: "Risk tolerance" })).toHaveValue("3");
  });
});
