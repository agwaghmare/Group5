/** Customer finance reads the signed-in synthetic tracker. There is no separate PNC banking API. */
import { readCustomerSession } from "@/lib/customer-session";

const BASE = (import.meta.env["VITE_PNC_API_URL"] as string | undefined) ?? "";
const PERSONA_KEY = "finpilot.customerId";

export interface Snapshot {
  date: string;
  user_id: number | string;
  monthly_income: number | string;
  income_volatility_3m: number | string;
  income_growth_6m: number | string;
  pay_frequency: string;
  months_employed: number | string;
  checking_balance: number | string;
  available_balance: number | string;
  overdraft_count_90d: number | string;
  recurring_bill_total: number | string;
  savings_balance: number | string;
  savings_apy: number | string;
  emergency_fund_months: number | string;
  monthly_savings_contribution: number | string;
  total_debt_balance: number | string;
  weighted_avg_apr: number | string;
  minimum_debt_payment: number | string;
  remaining_loan_term_months: number | string;
  credit_limit_total: number | string;
  credit_utilization: number | string;
  credit_card_apr: number | string;
  late_payments_12m: number | string;
  home_value: number | string;
  mortgage_balance: number | string;
  mortgage_interest_rate: number | string;
  home_equity: number | string;
  portfolio_value: number | string;
  equity_allocation_pct: number | string;
  retirement_contribution: number | string;
  subscription_cost_monthly: number | string;
  budget_variance_pct: number | string;
  savings_streak_months: number | string;
  liquidity_runway_months: number | string;
  projected_balance_30d: number | string;
  debt_service_coverage: number | string;
  bill_payment_delay_count: number | string;
  life_event_type: string;
}

export interface TrackerPayload {
  customer_id: string;
  snapshots: Snapshot[];
  total: number;
  source: string;
  synthetic: boolean;
}

export function setStoredCustomerId(id: string) {
  localStorage.setItem(PERSONA_KEY, id);
}

export async function loadTracker(): Promise<TrackerPayload> {
  const session = readCustomerSession();
  if (!session?.token) throw new Error("Sign in with a customer email to load tracker data.");
  const response = await fetch(`${BASE}/api/v1/pnc/tracker?limit=24`, {
    headers: { Accept: "application/json", Authorization: `Bearer ${session.token}` },
  });
  const payload = (await response.json().catch(() => ({}))) as TrackerPayload & { detail?: string };
  if (!response.ok) throw new Error(typeof payload.detail === "string" ? payload.detail : "Tracker data is unavailable.");
  return payload;
}

export interface AmeliaAnswer {
  answer: string;
  reasons: string[];
  limitations: string[];
  provider: string;
  status: string;
  agent: string;
}

function detailOf(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "Amelia could not complete this request.";
}

export async function askAmelia(featureId: string, question: string): Promise<AmeliaAnswer> {
  const session = readCustomerSession();
  if (!session?.token) throw new Error("Sign in with a customer email to ask Amelia.");
  const response = await fetch(`${BASE}/api/v1/pnc/assistant`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.token}`,
    },
    body: JSON.stringify({ feature_id: featureId, question }),
  });
  const payload = (await response.json().catch(() => ({}))) as AmeliaAnswer & { detail?: unknown };
  if (!response.ok) throw new Error(detailOf(payload.detail));
  return payload;
}

export function num(value: number | string | null | undefined): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : 0;
}

export function money(value: string | number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  }).format(n);
}

export function pct(value: number | null | undefined, asFraction = true): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  const n = asFraction ? value * 100 : value;
  return `${n.toFixed(1)}%`;
}
