import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  writeCustomerSession,
  type CustomerSession,
} from "@/lib/customer-session";
import { setStoredCustomerId } from "@/lib/finance-api";
import { rememberFifth } from "@/lib/fifth-page";
import { useCenterDrag } from "@/lib/use-center-drag";
import { TAB_LABEL, writeStaffToken, type StaffTab } from "@/lib/staff-api";

const KEYWORDS = [
  "Home",
  "APR",
  "Finance",
  "Learn",
  "Credit",
  "Savings",
  "Budget",
  "Equity",
];

type WheelPhase = "idle" | "burst" | "form" | "in";

function Ring({
  words,
  size,
  rOut,
  rIn,
  spinning,
}: {
  words: string[];
  size: number;
  rOut: number;
  rIn: number;
  spinning?: boolean;
}) {
  const c = size / 2;
  const step = 360 / words.length;
  const arc = (i: number) => {
    const a0 = ((i * step - step / 2 - 90 + 1.5) * Math.PI) / 180;
    const a1 = ((i * step + step / 2 - 90 - 1.5) * Math.PI) / 180;
    const p = (r: number, a: number) =>
      `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };
  return (
    <svg
      width={size}
      height={size}
      className={`pointer-events-none ${spinning ? "login-wheel" : ""}`}
      aria-hidden="true"
    >
      {words.map((word, i) => {
        const mid = ((i * step - 90) * Math.PI) / 180;
        const tr = (rOut + rIn) / 2;
        return (
          <g
            key={`${word}-${i}`}
            className="login-slice"
            style={{
              ["--dx" as string]: `${Math.cos(mid) * 1500}px`,
              ["--dy" as string]: `${Math.sin(mid) * 1500}px`,
            }}
          >
            <path
              d={arc(i)}
              className="pointer-events-auto fill-card stroke-border"
              strokeWidth={1.5}
            />
            <text
              x={c + tr * Math.cos(mid)}
              y={c + tr * Math.sin(mid)}
              textAnchor="middle"
              dominantBaseline="central"
              transform={`rotate(${i * step} ${c + tr * Math.cos(mid)} ${c + tr * Math.sin(mid)})`}
              className={`fill-primary font-sans font-semibold uppercase ${size > 400 ? "text-[13px]" : "text-[10px]"}`}
            >
              {word}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function KeywordWheel({
  phase,
  words,
  anchor,
  onCenter,
}: {
  phase: WheelPhase;
  words: string[];
  anchor: {
    x: number;
    y: number;
    size: number;
    rOut: number;
    rIn: number;
  } | null;
  onCenter: () => void;
}) {
  const drag = useCenterDrag(onCenter);
  if ((phase === "form" || phase === "in") && anchor) {
    return (
      <div
        className={`login-form-wheel pointer-events-none ${phase === "in" ? "is-in" : ""}`}
        style={{ left: anchor.x, top: anchor.y }}
      >
        <Ring
          words={words}
          size={anchor.size}
          rOut={anchor.rOut}
          rIn={anchor.rIn}
        />
      </div>
    );
  }
  return (
    <>
      <div
        aria-label="Drag the wheel to the center"
        className={`absolute touch-none select-none ${phase === "burst" ? "login-burst pointer-events-none" : "cursor-grab active:cursor-grabbing"} ${drag.opening ? "pointer-events-none" : ""}`}
        style={{
          transform: `translate(${drag.offset.x}px, ${drag.offset.y}px)`,
        }}
        {...(phase === "idle" ? drag.handlers : {})}
      >
        <Ring
          words={KEYWORDS}
          size={920}
          rOut={448}
          rIn={360}
          spinning={phase === "idle" && !drag.opening}
        />
      </div>
      {drag.revealProps && (
        <div
          aria-hidden="true"
          className="wheel-page-reveal"
          {...drag.revealProps}
        />
      )}
    </>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [docking, setDocking] = useState(false);
  const [phase, setPhase] = useState<WheelPhase>("idle");
  const [wheelWords, setWheelWords] = useState(KEYWORDS);
  const [anchor, setAnchor] = useState<{
    x: number;
    y: number;
    size: number;
    rOut: number;
    rIn: number;
  } | null>(null);

  const dockThen = (
    kind: "customer" | "employee",
    words: string[],
    go: () => void,
  ) => {
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (reduce) {
      go();
      return;
    }
    const pad = window.innerWidth >= 768 ? 24 : 16;
    const size = kind === "employee" ? 210 : 168;
    const edge = pad - 8;
    const outer = size + 24;
    setWheelWords(words);
    setAnchor({
      x: edge + outer / 2,
      y: window.innerHeight - edge - outer / 2,
      size,
      rOut: kind === "employee" ? 100 : 80,
      rIn: kind === "employee" ? 52 : 44,
    });
    setDocking(true);
    setPhase("burst");
    window.setTimeout(() => {
      setPhase("form");
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => setPhase("in"));
      });
    }, 740);
    window.setTimeout(go, 1720);
  };

  const enterCustomer = (session: CustomerSession) => {
    writeStaffToken(null);
    writeCustomerSession(session);
    if (session.customerId) setStoredCustomerId(session.customerId);
    dockThen("customer", ["Home", "Wallet", "Finance", "Learn"], () => void navigate({ to: "/" }));
  };

  const enterStaff = (session: CustomerSession, tabs: string[]) => {
    writeCustomerSession(session);
    writeStaffToken(session.token ?? null);
    const words = [
      ...tabs.filter((tab) => tab !== "learn" && tab !== "activity"),
      "activity",
    ].map((tab) => TAB_LABEL[tab as StaffTab] ?? tab);
    dockThen(
      "employee",
      words.length > 1 ? words : ["Home", "Research", "Benefits", "Activity"],
      () => void navigate({ to: "/employee" }),
    );
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const id = email.trim().toLowerCase();
    if (!id || docking || pending) return;
    const address = id;
    if (!address.includes("@")) {
      setError("Enter the email associated with your account.");
      return;
    }
    setError(null);
    setPending(true);
    void fetch("/api/v1/auth/login", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ email: address, password }),
    })
      .then(async (response) => {
        const payload = (await response.json().catch(() => ({}))) as {
          detail?: string;
          token?: string;
          user?: {
            email: string;
            role: string;
            role_label: string;
            display_name: string;
            customer_id: string | null;
            employee_id: string | null;
            is_staff: boolean;
            tabs?: string[];
          };
        };
        if (!response.ok || !payload.user || !payload.token) {
          setError(
            typeof payload.detail === "string"
              ? payload.detail
              : "That email is not a FinPilot account.",
          );
          setPending(false);
          return;
        }
        const session: CustomerSession = {
          email: payload.user.email,
          provider: "email",
          role: payload.user.role,
          roleLabel: payload.user.role_label,
          displayName: payload.user.display_name,
          customerId: payload.user.customer_id,
          employeeId: payload.user.employee_id,
          token: payload.token,
          isStaff: payload.user.is_staff,
        };
        queryClient.clear();
        if (!session.isStaff) writeStaffToken(null);
        if (payload.user.is_staff) enterStaff(session, payload.user.tabs ?? []);
        else enterCustomer(session);
      })
      .catch(() => {
        setError("The sign-in service is not reachable.");
        setPending(false);
      });
  };

  return (
    <div className="relative flex h-dvh items-center justify-center overflow-hidden bg-background">
      <KeywordWheel
        phase={phase}
        words={wheelWords}
        anchor={anchor}
        onCenter={() => {
          rememberFifth("login");
          void navigate({ to: "/page-five" });
        }}
      />
      <form
        onSubmit={submit}
        className={`login-card relative z-10 w-full max-w-sm rounded-[2rem] border border-border bg-background p-6 shadow-glow ${docking ? "is-docking" : ""}`}
      >
        <p className="font-display text-2xl font-extrabold">
          FIN<span className="text-primary">PILOT</span>
        </p>
        <h1 className="mt-2 font-display text-3xl font-extrabold leading-none">
          Sign in
        </h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Sign in to open the workspace assigned to your account. Drag the wheel
          into the center to see the rule behind it.
        </p>
        <label className="mt-4 block text-sm" htmlFor="login-email">
          Email
          <Input
            id="login-email"
            className="mt-1"
            type="email"
            required
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@company.com"
          />
        </label>
        <label className="mt-4 block text-sm" htmlFor="login-password">
          Password
          <Input
            id="login-password"
            className="mt-1"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <Button
          type="submit"
          className="mt-4 w-full"
          disabled={pending || docking}
        >
          {pending ? "Checking account…" : "Continue"}
        </Button>
      </form>
    </div>
  );
}
