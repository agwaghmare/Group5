import { useNavigate } from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { readCustomerSession, useCustomerSession } from "@/lib/customer-session";

export function RequireCustomer({ children }: { children: ReactNode }) {
  const session = useCustomerSession();
  const navigate = useNavigate();
  useEffect(() => {
    if (!readCustomerSession()) void navigate({ to: "/login", replace: true });
  }, [navigate, session]);
  if (!session) return null;
  return <>{children}</>;
}
