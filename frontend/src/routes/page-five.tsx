import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { FinpilotHeader } from "@/components/finpilot-header";
import { RequireCustomer } from "@/components/require-customer";
import { LandingPage } from "@/components/finpilot-landing";

export const Route = createFileRoute("/page-five")({
  head: () => ({ meta: [
    { title: "Page Five — FINPILOT" },
    { name: "description", content: "FINPILOT's fifth page." },
    { property: "og:title", content: "Page Five — FINPILOT" },
    { property: "og:description", content: "FINPILOT's fifth page." },
    { property: "og:type", content: "website" },
    { name: "twitter:card", content: "summary_large_image" },
  ] }),
  component: PageFive,
});

function PageFive() {
  const [returning, setReturning] = useState(false);
  const navigate = useNavigate();
  return (
    <RequireCustomer>
    <>
    {returning && <div className="pointer-events-none fixed inset-0" aria-hidden="true" inert><LandingPage /></div>}
    <div
      className={`relative flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6 ${returning ? "wheel-page-return pointer-events-none" : ""}`}
      onAnimationEnd={(e) => {
        if (returning && e.target === e.currentTarget) void navigate({ to: "/" });
      }}
    >
      <FinpilotHeader miniWheel onWheelReturn={() => setReturning(true)} />
      <main className="fifth-page-enter flex min-h-0 flex-1 flex-col justify-center rounded-[2rem] border border-border px-8 md:px-20">
        <p className="mb-4 font-display text-sm font-bold uppercase text-primary">05 — FINPILOT</p>
        <h1 className="font-display text-5xl font-extrabold md:text-7xl">Page Five</h1>
      </main>
    </div>
    </>
    </RequireCustomer>
  );
}