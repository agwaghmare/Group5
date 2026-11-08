const BASE =
  (import.meta.env["VITE_LEARN_API_URL"] as string | undefined) ?? "/api";

export class StaffError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export type StaffTab =
  | "home"
  | "research"
  | "cases"
  | "portfolio"
  | "compliance"
  | "benefits"
  | "activity"
  | "learn";

export interface Persona {
  id: string;
  role: string;
  display_name: string;
  synthetic: boolean;
}

export interface Employee {
  id: string;
  role: string;
  display_name: string;
  status: string;
  hire_date?: string;
  synthetic?: boolean;
}

export interface StaffSession {
  token: string;
  token_type: string;
  expires_at: string;
  employee: Employee;
  synthetic_demo: boolean;
  tabs: StaffTab[];
  features: string[];
  banner: string;
}

const TOKEN_KEY = "finpilot.staff.token";

export function readStaffToken() {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function writeStaffToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.sessionStorage.setItem(TOKEN_KEY, token);
  else window.sessionStorage.removeItem(TOKEN_KEY);
}

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: unknown }).message);
  }
  return "The staff request failed.";
}

export async function staffFetch<T>(
  path: string,
  init: {
    method?: string;
    body?: unknown;
    token?: string | null;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const token = init.token === undefined ? readStaffToken() : init.token;
  const headers: Record<string, string> = {};
  if (init.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const response = await fetch(`${BASE}/staff${path}`, {
    method: init.method ?? (init.body !== undefined ? "POST" : "GET"),
    headers,
    signal: init.signal ?? null,
    ...(init.body !== undefined ? { body: JSON.stringify(init.body) } : {}),
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new StaffError(response.status, detailMessage(payload.detail));
  }
  return payload as T;
}

export const TAB_LABEL: Record<StaffTab, string> = {
  home: "Home",
  research: "Research",
  cases: "Cases",
  portfolio: "Portfolio",
  compliance: "Compliance",
  benefits: "Benefits",
  activity: "Activity",
  learn: "Learn",
};

export const ROLE_LABEL: Record<string, string> = {
  credit_analyst: "Credit Analyst",
  service_specialist: "Service Specialist",
  marketing_analyst: "Marketing Analyst",
  portfolio_manager: "Portfolio Manager",
  compliance_analyst: "Compliance Analyst",
  auditor: "Auditor",
  benefits_admin: "Benefits Admin",
};

export const DECISIONS = [
  "Proceed to next step (simulated)",
  "Request more information",
  "Refer to senior review",
  "Decline as entered (with reason codes)",
] as const;
