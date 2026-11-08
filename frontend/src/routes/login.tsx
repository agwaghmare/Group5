import { createFileRoute } from "@tanstack/react-router";
import { LoginPage } from "@/components/login-page";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — FINPILOT" },
      { name: "description", content: "Sign in to FINPILOT with your email or Google, or open the employee desk." },
    ],
  }),
  component: LoginPage,
});
