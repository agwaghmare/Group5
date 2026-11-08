import { createFileRoute } from "@tanstack/react-router";
import { LandingPage } from "@/components/finpilot-landing";
import { RequireCustomer } from "@/components/require-customer";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "FINPILOT — Navigate your finances" },
      { name: "description", content: "FINPILOT helps you steer home, auto and finance in one place." },
      { property: "og:title", content: "FINPILOT — Navigate your finances" },
      { property: "og:description", content: "Steer home, auto and finance in one place." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: () => (
    <RequireCustomer>
      <LandingPage />
    </RequireCustomer>
  ),
});

