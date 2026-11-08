import { readCustomerSession } from "./customer-session";

export interface InvestmentProfile {
  goal: string; horizon_months: number; tolerance: number; liquidity_need_cents: number; target_return: number;
}
export interface PortfolioAssessment {
  allocations: { stocks: number; bonds: number; foreign: number };
  metrics: { annualized_return: number; volatility: number; max_drawdown: number; total_return: number };
  risk_budget: number; risk_capacity: string; flags: string[]; binding_limits: string[];
  return_history: { date: string; portfolio_index: number; benchmark_index: number }[];
  profile_model?: { allocations: PortfolioAssessment["allocations"]; metrics: PortfolioAssessment["metrics"];
    goal_feasible: boolean; same_as_current: boolean; requires_approval: boolean } | null;
  missing_inputs?: string[];
}
export interface CustomerPortfolio {
  client_id: number; value_cents: number; as_of: string;
  allocations: PortfolioAssessment["allocations"]; profile: InvestmentProfile;
  holdings: { bucket: string; instrument: string; value_cents: number }[];
  assessment: PortfolioAssessment; disclaimer: string;
}
const BASE = (import.meta.env["VITE_PNC_API_URL"] as string | undefined) ?? "";
async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const session = readCustomerSession();
  if (!session?.token) throw new Error("Sign in to view your investments.");
  const response = await fetch(`${BASE}/api/v1/pnc/portfolio${path}`, {
    method: body === undefined ? "GET" : "POST", signal: signal ?? null,
    headers: { Authorization: `Bearer ${session.token}`, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "The investment preview could not be calculated.");
  return payload;
}
export const loadCustomerPortfolio = () => request<CustomerPortfolio>("");
export function editableInvestmentProfile(profile: InvestmentProfile): InvestmentProfile {
  return { goal: profile.goal, horizon_months: profile.horizon_months, tolerance: profile.tolerance,
    liquidity_need_cents: profile.liquidity_need_cents, target_return: profile.target_return };
}
export const previewCustomerPortfolio = (body: { allocations: PortfolioAssessment["allocations"]; profile: InvestmentProfile; investment_cents: number }, signal?: AbortSignal) =>
  request<{ assessment: PortfolioAssessment; preview_only: boolean }>("/preview", body, signal);

export function allocationAmounts(totalCents: number, weights: PortfolioAssessment["allocations"]) {
  const buckets = ["stocks", "bonds", "foreign"] as const;
  const parts = buckets.map((bucket) => ({ bucket, raw: totalCents * weights[bucket], cents: Math.floor(totalCents * weights[bucket]) }));
  let remainder = totalCents - parts.reduce((sum, part) => sum + part.cents, 0);
  for (const part of [...parts].sort((a, b) => (b.raw - b.cents) - (a.raw - a.cents))) {
    if (remainder-- > 0) part.cents += 1;
  }
  return Object.fromEntries(parts.map((part) => [part.bucket, part.cents])) as Record<typeof buckets[number], number>;
}

export function investmentProjection(principal: number, monthly: number, annualReturn: number, months: number) {
  const rate = Math.expm1(Math.log1p(annualReturn) / 12);
  let balance = principal;
  const points = [{ label: "Now", Balance: balance, Contributions: balance }];
  for (let month = 1; month <= months; month++) {
    balance = balance * (1 + rate) + monthly;
    points.push({ label: String(month), Balance: balance, Contributions: principal + monthly * month });
  }
  return { ending: balance, contributed: principal + monthly * months, points };
}
