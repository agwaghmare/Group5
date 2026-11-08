import { useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { writeCustomerSession, type CustomerSession } from "@/lib/customer-session";
import { setStoredCustomerId } from "@/lib/finance-api";
import { TAB_LABEL, writeStaffToken, type StaffTab } from "@/lib/staff-api";

const KEYWORDS = ["Home", "APR", "Finance", "Learn", "Credit", "Savings", "Budget", "Equity"];

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (config: { client_id: string; callback: (response: { credential: string }) => void }) => void;
          prompt: (callback: (notification: { isNotDisplayed: () => boolean; isSkippedMoment: () => boolean }) => void) => void;
          renderButton: (parent: HTMLElement, options: Record<string, string | number>) => void;
        };
      };
    };
  }
}

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
    const p = (r: number, a: number) => `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };
  return (
    <svg width={size} height={size} className={spinning ? "login-wheel" : undefined} aria-hidden="true">
      {words.map((word, i) => {
        const mid = ((i * step - 90) * Math.PI) / 180;
        const tr = (rOut + rIn) / 2;
        return (
          <g
            key={`${word}-${i}`}
            className="login-slice"
            style={{ ["--dx" as string]: `${Math.cos(mid) * 1500}px`, ["--dy" as string]: `${Math.sin(mid) * 1500}px` }}
          >
            <path d={arc(i)} className="fill-card stroke-border" strokeWidth={1.5} />
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
}: {
  phase: WheelPhase;
  words: string[];
  anchor: { x: number; y: number; size: number; rOut: number; rIn: number } | null;
}) {
  if ((phase === "form" || phase === "in") && anchor) {
    return (
      <div className={`login-form-wheel pointer-events-none ${phase === "in" ? "is-in" : ""}`} style={{ left: anchor.x, top: anchor.y }}>
        <Ring words={words} size={anchor.size} rOut={anchor.rOut} rIn={anchor.rIn} />
      </div>
    );
  }
  return (
    <div className={`pointer-events-none absolute ${phase === "burst" ? "login-burst" : ""}`}>
      <Ring words={KEYWORDS} size={920} rOut={448} rIn={360} spinning={phase === "idle"} />
    </div>
  );
}

function emailOf(credential: string) {
  const payload = credential.split(".")[1];
  if (!payload) return null;
  try {
    const parsed = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/"))) as { email?: string };
    return parsed.email ?? null;
  } catch {
    return null;
  }
}

export function LoginPage() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [googlePending, setGooglePending] = useState(false);
  const [pending, setPending] = useState(false);
  const [docking, setDocking] = useState(false);
  const [phase, setPhase] = useState<WheelPhase>("idle");
  const [wheelWords, setWheelWords] = useState(KEYWORDS);
  const [anchor, setAnchor] = useState<{ x: number; y: number; size: number; rOut: number; rIn: number } | null>(null);

  const dockThen = (kind: "customer" | "employee", words: string[], go: () => void) => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
    dockThen("customer", ["Home", "Auto", "Finance", "Learn"], () => void navigate({ to: "/" }));
  };

  const enterStaff = (session: CustomerSession, tabs: string[]) => {
    writeCustomerSession(session);
    writeStaffToken(session.token ?? null);
    const words = [...tabs.filter((tab) => tab !== "learn" && tab !== "activity"), "activity"].map(
      (tab) => TAB_LABEL[tab as StaffTab] ?? tab,
    );
    dockThen("employee", words.length > 1 ? words : ["Home", "Research", "Benefits", "Activity"], () => void navigate({ to: "/employee" }));
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const id = email.trim().toLowerCase();
    if (!id || docking || pending) return;
    const address =
      id === "customer" ? "customer1000@example.test" : id === "employee" ? "e001@example.test" : id;
    if (!address.includes("@")) {
      setError("Use an account email, such as customer1000@example.test or e001@example.test.");
      return;
    }
    setError(null);
    setPending(true);
    void fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ email: address, password: "demo" }),
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
          setError(typeof payload.detail === "string" ? payload.detail : "That email is not a FinPilot account.");
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
        if (payload.user.is_staff) enterStaff(session, payload.user.tabs ?? []);
        else enterCustomer(session);
      })
      .catch(() => {
        setError("The sign-in service is not reachable.");
        setPending(false);
      });
  };

  const google = () => {
    const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID as string | undefined;
    if (!clientId) {
      setError("Add VITE_GOOGLE_CLIENT_ID to sign in with Google.");
      return;
    }
    setGooglePending(true);
    setError(null);
    const finish = (credential: string) => {
      const address = emailOf(credential);
      setGooglePending(false);
      if (!address) {
        setError("Google did not return an email.");
        return;
      }
      enterCustomer({ email: address, provider: "google" });
    };
    const start = () => {
      const googleApi = window.google?.accounts?.id;
      if (!googleApi) {
        setGooglePending(false);
        setError("Google sign-in did not load.");
        return;
      }
      googleApi.initialize({ client_id: clientId, callback: (response) => finish(response.credential) });
      googleApi.prompt((notification) => {
        if (notification.isNotDisplayed() || notification.isSkippedMoment()) {
          const holder = document.getElementById("google-signin");
          if (holder) googleApi.renderButton(holder, { theme: "filled_black", size: "large", text: "continue_with", width: 280 });
          setGooglePending(false);
        }
      });
    };
    if (window.google?.accounts?.id) {
      start();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.onload = start;
    script.onerror = () => {
      setGooglePending(false);
      setError("Google sign-in did not load.");
    };
    document.head.appendChild(script);
  };

  return (
    <div className="relative flex h-dvh items-center justify-center overflow-hidden bg-background">
      <KeywordWheel phase={phase} words={wheelWords} anchor={anchor} />
      <form onSubmit={submit} className={`login-card relative z-10 w-full max-w-sm rounded-[2rem] border border-border bg-background p-6 shadow-glow ${docking ? "is-docking" : ""}`}>
        <p className="font-display text-2xl font-extrabold">FIN<span className="text-primary">PILOT</span></p>
        <h1 className="mt-2 font-display text-3xl font-extrabold leading-none">Sign in</h1>
        <p className="mt-2 text-sm text-muted-foreground">Each email opens that account. Customers use customer1000@example.test and up. Employees use e001@example.test through e008@example.test.</p>
        <label className="mt-4 block text-sm" htmlFor="login-email">
          Email
          <Input
            id="login-email"
            className="mt-1"
            type="text"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="customer1000@example.test"
          />
        </label>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <Button type="submit" className="mt-4 w-full" disabled={pending || docking}>{pending ? "Checking account…" : "Continue"}</Button>
        <Button type="button" variant="outline" className="mt-2 w-full" disabled={googlePending} onClick={google}>
          {googlePending ? "Opening Google…" : "Continue with Google"}
        </Button>
        <div id="google-signin" className="mt-2 flex justify-center" />
      </form>
    </div>
  );
}
