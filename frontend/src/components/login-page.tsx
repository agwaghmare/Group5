import { useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  writeCustomerSession,
  type CustomerSession,
} from "@/lib/customer-session";
import { setStoredCustomerId } from "@/lib/finance-api";
import { writeStaffToken } from "@/lib/staff-api";

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

function KeywordWheel({
  wheelRef,
  docking,
}: {
  wheelRef: React.RefObject<HTMLDivElement | null>;
  docking: boolean;
}) {
  const size = 920;
  const c = size / 2;
  const rOut = 448;
  const rIn = 360;
  const step = 360 / KEYWORDS.length;
  const arc = (i: number) => {
    const a0 = ((i * step - step / 2 - 90 + 1.5) * Math.PI) / 180;
    const a1 = ((i * step + step / 2 - 90 - 1.5) * Math.PI) / 180;
    const p = (r: number, a: number) =>
      `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };
  return (
    <div
      ref={wheelRef}
      className={`login-wheel-dock pointer-events-none absolute ${docking ? "is-docking" : ""}`}
      aria-hidden="true"
    >
      <div className="login-wheel">
        <svg width={size} height={size}>
          {KEYWORDS.map((word, i) => {
            const mid = ((i * step - 90) * Math.PI) / 180;
            const tr = (rOut + rIn) / 2;
            return (
              <g key={word}>
                <path
                  d={arc(i)}
                  className="fill-card stroke-border"
                  strokeWidth={1.5}
                />
                <text
                  x={c + tr * Math.cos(mid)}
                  y={c + tr * Math.sin(mid)}
                  textAnchor="middle"
                  dominantBaseline="central"
                  transform={`rotate(${i * step} ${c + tr * Math.cos(mid)} ${c + tr * Math.sin(mid)})`}
                  className="fill-primary font-display text-[13px] font-bold uppercase"
                >
                  {word}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

export function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const wheelRef = useRef<HTMLDivElement>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [docking, setDocking] = useState(false);

  const dockThen = (kind: "customer" | "employee", go: () => void) => {
    const node = wheelRef.current;
    const reduce = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    if (!node || reduce) {
      go();
      return;
    }
    const rect = node.getBoundingClientRect();
    const pad = window.innerWidth >= 768 ? 24 : 16;
    const size = kind === "employee" ? 234 : 192;
    const edge = pad - 8;
    const targetX = edge + size / 2;
    const targetY = window.innerHeight - edge - size / 2;
    node.style.setProperty(
      "--dock-x",
      `${targetX - (rect.left + rect.width / 2)}px`,
    );
    node.style.setProperty(
      "--dock-y",
      `${targetY - (rect.top + rect.height / 2)}px`,
    );
    node.style.setProperty("--dock-scale", `${size / rect.width}`);
    setDocking(true);
    const finish = (event: TransitionEvent) => {
      if (event.propertyName !== "transform") return;
      node.removeEventListener("transitionend", finish);
      go();
    };
    node.addEventListener("transitionend", finish);
  };

  const enterCustomer = (session: CustomerSession) => {
    writeStaffToken(null);
    writeCustomerSession(session);
    if (session.customerId) setStoredCustomerId(session.customerId);
    dockThen("customer", () => void navigate({ to: "/" }));
  };

  const enterStaff = (session: CustomerSession) => {
    writeCustomerSession(session);
    writeStaffToken(session.token ?? null);
    dockThen("employee", () => void navigate({ to: "/employee" }));
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
        if (payload.user.is_staff) enterStaff(session);
        else enterCustomer(session);
      })
      .catch(() => {
        setError("The sign-in service is not reachable.");
        setPending(false);
      });
  };

  return (
    <div className="relative flex h-dvh items-center justify-center overflow-hidden bg-background">
      <KeywordWheel wheelRef={wheelRef} docking={docking} />
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
          Sign in to open the workspace assigned to your account.
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
