/** Typed client for the PNC customer API (`/api/v1/pnc`). Auth is a demo bearer from `/api/v1/auth/dev-login`. */

const BASE =
  (import.meta.env["VITE_PNC_API_URL"] as string | undefined) ?? "";

const PERSONA_KEY = "finpilot.customerId";
const TOKEN_KEY = "finpilot.pncToken";

export type CustomerId = `C${string}`;

export interface Profile {
  customer_id: string;
  display_name: string;
  age: number | null;
  city: string | null;
  pay_frequency: string;
  annual_income: string;
  credit_score: number | null;
  preferred_channel: string | null;
  source_type: string;
}

export interface Account {
  account_id: string;
  account_type: string;
  name: string;
  balance: string;
  apr_pct: string | null;
  apy_pct: string | null;
  credit_limit: string | null;
  required_monthly_payment: string | null;
  opened_date: string | null;
}

export interface Indicator {
  id: string;
  label: string;
  unit: string;
  raw: number | null;
  normalized: number;
  status: "risk" | "watch" | "ok" | "strong" | "unavailable";
  explanation: string;
  source: string;
  safe_action: string;
}

export interface XRay {
  as_of: string;
  customer_id: string;
  overall: {
    score: number;
    band: string;
    disclaimer: string;
    indicators_used: number;
    indicators_total: number;
  };
  indicators: Indicator[];
}

export interface CashMonth {
  month: string;
  income: string;
  consumption_spending: string;
  essential_spending: string;
  discretionary_spending: string;
  debt_payments: string;
  savings_transfers_out: string;
  card_settlements: string;
}

export interface EvidenceBlock {
  name: string;
  as_of_date: string;
  results: Record<string, unknown>;
  assumptions: string[];
  formula_steps: string[];
  limitations: string[];
  inputs: Record<string, unknown>;
}

export interface Forecast {
  model: string;
  selection_reason: string;
  unit: string;
  disclaimer: string;
  forecast: { month_ahead: number; point: number; low_80: number; high_80: number }[];
}

export interface Mission {
  mission_id: string;
  title: string;
  why: string;
  linked_indicator: string;
  optional: boolean;
}

export interface Obligation {
  kind: string;
  amount: string;
  due: string;
}

export interface Goal {
  goal_id: string;
  name: string;
  target_amount: string;
  starting_amount: string;
  current_amount: string;
  deadline: string;
  planned_monthly_contribution: string | null;
  status: string;
}

export interface PurchaseResult {
  baseline: EvidenceBlock;
  scenario: EvidenceBlock;
  saved: unknown;
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail?.reason) return body.detail.reason;
    if (Array.isArray(body?.detail)) return body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ");
    return JSON.stringify(body).slice(0, 200);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

async function request<T>(path: string, init: RequestInit = {}, customerId?: string): Promise<T> {
  const token = await ensureToken(customerId);
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      Authorization: `Bearer ${token}`,
      ...(init.headers ?? {}),
    },
  });
  if (res.status === 401) {
    clearToken();
    const retry = await ensureToken(customerId);
    const again = await fetch(`${BASE}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        Authorization: `Bearer ${retry}`,
        ...(init.headers ?? {}),
      },
    });
    if (!again.ok) throw new Error(await parseError(again));
    return again.json() as Promise<T>;
  }
  if (!res.ok) throw new Error(await parseError(res));
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function getStoredCustomerId(): string {
  if (typeof window === "undefined") return "C001";
  return localStorage.getItem(PERSONA_KEY) || "C001";
}

export function setStoredCustomerId(id: string) {
  localStorage.setItem(PERSONA_KEY, id);
  clearToken();
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

async function ensureToken(customerId?: string): Promise<string> {
  const id = customerId || getStoredCustomerId();
  const cached = localStorage.getItem(TOKEN_KEY);
  if (cached) {
    try {
      const payload = JSON.parse(atob(cached.split(".")[1] ?? ""));
      const matches =
        payload.customer_id === id || payload.sub === id || payload.login_name === String(id).toLowerCase();
      if (matches && payload.exp * 1000 > Date.now() + 30_000) return cached;
    } catch {
      /* re-login */
    }
  }
  const res = await fetch(`${BASE}/api/v1/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ persona_id: id }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const data = (await res.json()) as {
    access_token: string;
    user?: { role: string; tabs: string[]; home_route: string; customer_id?: string };
  };
  localStorage.setItem(TOKEN_KEY, data.access_token);
  if (data.user) {
    localStorage.setItem("finpilot.user", JSON.stringify(data.user));
  }
  return data.access_token;
}

export const CUSTOMERS = Array.from({ length: 30 }, (_, i) => `C${String(i + 1).padStart(3, "0")}`);

export const financeApi = {
  profile: () => request<Profile>("/api/v1/pnc/profile"),
  accounts: () => request<{ as_of: string; accounts: Account[] }>("/api/v1/pnc/accounts"),
  xray: () => request<XRay>("/api/v1/pnc/financial-xray"),
  cashFlow: (months = 12) => request<{ as_of: string; months: CashMonth[] }>(`/api/v1/pnc/cash-flow?months=${months}`),
  safeSpend: () => request<EvidenceBlock>("/api/v1/pnc/safe-spend"),
  missions: () => request<{ as_of: string; missions: Mission[] }>("/api/v1/pnc/missions"),
  obligations: (days = 30) =>
    request<{ as_of: string; days: number; obligations: Obligation[] }>(`/api/v1/pnc/upcoming-obligations?days=${days}`),
  forecast: () => request<Forecast>("/api/v1/pnc/forecasts/balances?months=3"),
  stress: () => request<Record<string, unknown>>("/api/v1/pnc/forecasts/stress"),
  payoff: (extra = 100) => request<EvidenceBlock>(`/api/v1/pnc/debt/payoff-compare?extra_monthly=${extra}`),
  amortize: (accountId: string) =>
    request<EvidenceBlock>(`/api/v1/pnc/debt/amortization?account_id=${encodeURIComponent(accountId)}`),
  goals: () => request<{ goals: Goal[] }>("/api/v1/pnc/goals"),
  createGoal: (body: {
    name: string;
    target_amount: number;
    starting_amount?: number;
    deadline: string;
    planned_monthly_contribution?: number | null;
  }) =>
    request<{ goal_id?: string; goal?: Goal } | Goal>("/api/v1/pnc/goals", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteGoal: (id: string) => request<unknown>(`/api/v1/pnc/goals/${id}`, { method: "DELETE" }),
  planGoal: (id: string) =>
    request<Record<string, unknown>>(`/api/v1/pnc/goals/${id}/calculate-plan`, { method: "POST" }),
  purchase: (body: {
    price: number;
    down_payment: number;
    apr_pct: number;
    term_months: number;
    save?: boolean;
  }) =>
    request<PurchaseResult>("/api/v1/pnc/scenarios/purchase", {
      method: "POST",
      body: JSON.stringify({ ...body, save: false }),
    }),
};

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

export function statusTone(status: string): string {
  switch (status) {
    case "strong":
      return "text-primary";
    case "ok":
      return "text-foreground";
    case "watch":
      return "text-amber-300";
    case "risk":
      return "text-destructive";
    default:
      return "text-muted-foreground";
  }
}
