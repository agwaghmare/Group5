import { useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { writeCustomerSession } from "@/lib/customer-session";

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
    const p = (r: number, a: number) => `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };
  return (
    <div ref={wheelRef} className={`login-wheel-dock pointer-events-none absolute ${docking ? "is-docking" : ""}`} aria-hidden="true">
      <div className="login-wheel">
      <svg width={size} height={size}>
        {KEYWORDS.map((word, i) => {
          const mid = ((i * step - 90) * Math.PI) / 180;
          const tr = (rOut + rIn) / 2;
          return (
            <g key={word}>
              <path d={arc(i)} className="fill-card stroke-border" strokeWidth={1.5} />
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
  const wheelRef = useRef<HTMLDivElement>(null);
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [googlePending, setGooglePending] = useState(false);
  const [docking, setDocking] = useState(false);

  const dockThen = (kind: "customer" | "employee", go: () => void) => {
    const node = wheelRef.current;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
    node.style.setProperty("--dock-x", `${targetX - (rect.left + rect.width / 2)}px`);
    node.style.setProperty("--dock-y", `${targetY - (rect.top + rect.height / 2)}px`);
    node.style.setProperty("--dock-scale", `${size / rect.width}`);
    setDocking(true);
    const finish = (event: TransitionEvent) => {
      if (event.propertyName !== "transform") return;
      node.removeEventListener("transitionend", finish);
      go();
    };
    node.addEventListener("transitionend", finish);
  };

  const enterCustomer = (address: string, provider: "email" | "google") => {
    writeCustomerSession({ email: address, provider });
    dockThen("customer", () => void navigate({ to: "/" }));
  };

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const id = email.trim().toLowerCase();
    if (!id) {
      setError("Type customer or employee.");
      return;
    }
    setError(null);
    if (id === "employee") {
      dockThen("employee", () => void navigate({ to: "/employee" }));
      return;
    }
    enterCustomer(id === "customer" ? "customer" : id, "email");
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
      enterCustomer(address, "google");
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
      <KeywordWheel wheelRef={wheelRef} docking={docking} />
      <form onSubmit={submit} className={`login-card relative z-10 w-full max-w-sm rounded-[2rem] border border-border bg-background p-6 shadow-glow ${docking ? "is-docking" : ""}`}>
        <p className="font-display text-2xl font-extrabold">FIN<span className="text-primary">PILOT</span></p>
        <h1 className="mt-2 font-display text-3xl font-extrabold leading-none">Sign in</h1>
        <p className="mt-2 text-sm text-muted-foreground">Type customer or employee. No password for now.</p>
        <label className="mt-4 block text-sm" htmlFor="login-email">
          Sign in
          <Input
            id="login-email"
            className="mt-1"
            type="text"
            autoComplete="username"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="customer or employee"
          />
        </label>
        {error && <p className="mt-3 text-sm text-destructive">{error}</p>}
        <Button type="submit" className="mt-4 w-full">Continue</Button>
        <Button type="button" variant="outline" className="mt-2 w-full" disabled={googlePending} onClick={google}>
          {googlePending ? "Opening Google…" : "Continue with Google"}
        </Button>
        <div id="google-signin" className="mt-2 flex justify-center" />
      </form>
    </div>
  );
}
