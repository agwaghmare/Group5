import { useSyncExternalStore } from "react";

const KEY = "finpilot.customer";

export interface CustomerSession {
  email: string;
  provider: "email" | "google";
}

const listeners = new Set<() => void>();
let cachedRaw: string | null | undefined;
let cachedSession: CustomerSession | null = null;

function emit() {
  listeners.forEach((listener) => listener());
}

export function readCustomerSession(): CustomerSession | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(KEY);
  if (raw === cachedRaw) return cachedSession;
  cachedRaw = raw;
  if (!raw) {
    cachedSession = null;
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as CustomerSession;
    cachedSession = parsed.email ? parsed : null;
  } catch {
    cachedSession = null;
  }
  return cachedSession;
}

export function writeCustomerSession(session: CustomerSession | null) {
  if (typeof window === "undefined") return;
  if (session) {
    const raw = JSON.stringify(session);
    window.sessionStorage.setItem(KEY, raw);
    cachedRaw = raw;
    cachedSession = session;
  } else {
    window.sessionStorage.removeItem(KEY);
    cachedRaw = null;
    cachedSession = null;
  }
  emit();
}

export function useCustomerSession() {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    readCustomerSession,
    () => null,
  );
}
