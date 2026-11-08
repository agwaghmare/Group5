import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { CenterBrief } from "@/components/center-brief";
import { LandingPage } from "@/components/finpilot-landing";
import { RequireCustomer } from "@/components/require-customer";
import { readFifth } from "@/lib/fifth-page";

export const Route = createFileRoute("/page-five")({
  head: () => ({
    meta: [
      { title: "The center — FINPILOT" },
      {
        name: "description",
        content: "The model explains. A person records the decision.",
      },
    ],
  }),
  component: PageFive,
});

function wheelHome() {
  const pad = window.innerWidth >= 768 ? 24 : 16;
  const size = 192;
  const edge = pad - 8;
  return { x: edge + size / 2, y: window.innerHeight - edge - size / 2 };
}

function PageFive() {
  const from = readFifth();
  const [origin, setOrigin] = useState<{ x: number; y: number } | null>(null);
  const navigate = useNavigate();
  const leave = () => {
    if (from === "employee") void navigate({ to: "/employee" });
    else if (from === "login") void navigate({ to: "/login" });
    else void navigate({ to: "/" });
  };
  if (from === "employee" || from === "login") {
    return (
      <>
        {!origin && (
          <CenterBrief from={from} onReturn={() => setOrigin(wheelHome())} />
        )}
        {origin && (
          <div
            className="wheel-page-return-ring"
            style={{ left: origin.x, top: origin.y }}
            onAnimationEnd={(event) => {
              if (event.target === event.currentTarget) leave();
            }}
          />
        )}
      </>
    );
  }
  return (
    <RequireCustomer>
      <>
        {origin && (
          <div
            className="pointer-events-none fixed inset-0 z-40"
            aria-hidden="true"
            inert
          >
            <LandingPage />
          </div>
        )}
        {!origin && (
          <CenterBrief
            from="customer"
            onReturn={() => setOrigin(wheelHome())}
          />
        )}
        {origin && (
          <div
            className="wheel-page-return-ring"
            style={{ left: origin.x, top: origin.y }}
            onAnimationEnd={(event) => {
              if (event.target === event.currentTarget)
                void navigate({ to: "/" });
            }}
          />
        )}
      </>
    </RequireCustomer>
  );
}
