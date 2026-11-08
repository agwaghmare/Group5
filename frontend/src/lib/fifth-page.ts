const KEY = "finpilot.fifth-from";

export type FifthFrom = "customer" | "employee" | "login";

export function rememberFifth(from: FifthFrom) {
  if (typeof window === "undefined") return;
  window.sessionStorage.setItem(KEY, from);
}

export function readFifth(): FifthFrom {
  if (typeof window === "undefined") return "customer";
  const value = window.sessionStorage.getItem(KEY);
  if (value === "employee" || value === "login") return value;
  return "customer";
}
