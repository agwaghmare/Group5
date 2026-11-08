import { useNavigate } from "@tanstack/react-router";
import { useEffect, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  readCustomerSession,
  useCustomerSession,
} from "@/lib/customer-session";

export function RequireCustomer({ children }: { children: ReactNode }) {
  const session = useCustomerSession();
  const navigate = useNavigate();
  const identity = useQuery({
    queryKey: ["identity", session?.token],
    enabled: Boolean(session?.token),
    retry: false,
    queryFn: async () => {
      const response = await fetch("/api/v1/auth/me", {
        headers: { Authorization: `Bearer ${session?.token}` },
      });
      if (!response.ok) throw new Error("Sign in again");
      return response.json() as Promise<{ is_staff: boolean }>;
    },
  });
  useEffect(() => {
    if (!readCustomerSession()?.token || identity.error)
      void navigate({ to: "/login", replace: true });
    else if (identity.data?.is_staff)
      void navigate({ to: "/employee", replace: true });
  }, [navigate, session, identity.data, identity.error]);
  if (!session?.token || !identity.data || identity.data.is_staff) return null;
  return <>{children}</>;
}
