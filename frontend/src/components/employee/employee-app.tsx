import { useNavigate } from "@tanstack/react-router";
import { writeCustomerSession } from "@/lib/customer-session";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { FinpilotHeader } from "@/components/finpilot-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  DECISIONS,
  ROLE_LABEL,
  StaffError,
  TAB_LABEL,
  readStaffToken,
  staffFetch,
  writeStaffToken,
  type StaffSession,
  type StaffTab,
} from "@/lib/staff-api";

function messageOf(error: unknown) {
  if (error instanceof StaffError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

function statusOf(error: unknown) {
  return error instanceof StaffError ? error.status : 0;
}

function PanelState({
  loading,
  error,
  empty,
  children,
}: {
  loading: boolean;
  error: unknown;
  empty?: boolean;
  children: React.ReactNode;
}) {
  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (statusOf(error) === 401) {
    return (
      <p className="text-sm text-destructive">
        Your session expired. Sign in again.
      </p>
    );
  }
  if (statusOf(error) === 403) {
    return (
      <p className="text-sm text-destructive">Not available for this role.</p>
    );
  }
  if (error)
    return <p className="text-sm text-destructive">{messageOf(error)}</p>;
  if (empty)
    return (
      <p className="text-sm text-muted-foreground">Nothing is assigned yet.</p>
    );
  return <>{children}</>;
}

function QuickActions({
  items,
}: {
  items: { label: string; detail: string; onClick: () => void }[];
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          onClick={item.onClick}
          className="rounded-2xl border border-border px-4 py-3 text-left hover:border-primary"
        >
          <span className="block font-display text-sm font-bold">
            {item.label}
          </span>
          <span className="text-xs text-muted-foreground">{item.detail}</span>
        </button>
      ))}
    </div>
  );
}

function BessieRail({
  featureId,
  resourceId,
  hint,
}: {
  featureId: string;
  resourceId?: string | undefined;
  hint: string;
}) {
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<{ question: string; answer: string }[]>(
    [],
  );
  const prompts = [
    "Why does this need review?",
    "What is missing?",
    "What would change the outcome?",
  ];
  const ask = (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setPending(true);
    setError(null);
    void staffFetch<{ answer: string; provider: string; status: string }>(
      "/assistant",
      {
        body: {
          feature_id: featureId,
          resource_id: resourceId,
          question: trimmed,
        },
      },
    )
      .then((row) => {
        setTurns((current) => [
          ...current,
          {
            question: trimmed,
            answer: `${row.answer} (${row.provider} · ${row.status})`,
          },
        ]);
        setQuestion("");
      })
      .catch((err) => setError(messageOf(err)))
      .finally(() => setPending(false));
  };
  return (
    <aside className="flex h-full w-full flex-col border-border bg-background p-4 lg:w-80 lg:border-l">
      <p className="font-display text-lg font-extrabold">Bessie</p>
      <p className="text-xs text-muted-foreground">
        Mistral-backed explanations of the evidence your role can access.
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            className="rounded-full border border-border px-3 py-1 text-left text-xs hover:border-primary"
            onClick={() => ask(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
      <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto">
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Answers stay on this side of the desk.
          </p>
        )}
        {turns.map((turn, index) => (
          <article
            key={index}
            className="rounded-2xl border border-border p-3 text-sm"
          >
            <p className="font-display font-bold">{turn.question}</p>
            <p className="mt-1 text-muted-foreground">{turn.answer}</p>
          </article>
        ))}
      </div>
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          ask(question);
        }}
      >
        <Textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask Bessie"
          aria-label="Ask Bessie"
          rows={3}
        />
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" disabled={pending || !question.trim()}>
          {pending ? "Asking…" : "Ask Bessie"}
        </Button>
      </form>
    </aside>
  );
}

function EmployeeWheel({
  tabs,
  progress,
  onSelect,
}: {
  tabs: StaffTab[];
  progress: number;
  onSelect: (index: number) => void;
}) {
  const step = 360 / tabs.length;
  const active = Math.round(progress);
  const size = 210;
  const c = size / 2;
  const rOut = 100;
  const rIn = 52;
  const arc = (i: number) => {
    const a0 = ((i * step - step / 2 - 90 + 2) * Math.PI) / 180;
    const a1 = ((i * step + step / 2 - 90 - 2) * Math.PI) / 180;
    const p = (r: number, a: number) =>
      `${c + r * Math.cos(a)} ${c + r * Math.sin(a)}`;
    return `M ${p(rOut, a0)} A ${rOut} ${rOut} 0 0 1 ${p(rOut, a1)} L ${p(rIn, a1)} A ${rIn} ${rIn} 0 0 0 ${p(rIn, a0)} Z`;
  };
  return (
    <div
      className="relative rounded-full bg-background p-3 shadow-glow"
      style={{ width: size + 24, height: size + 24 }}
    >
      <svg
        width={size}
        height={size}
        style={{ transform: `rotate(${-progress * step}deg)` }}
      >
        {tabs.map((tab, i) => {
          const mid = ((i * step - 90) * Math.PI) / 180;
          const tr = (rOut + rIn) / 2;
          const label = TAB_LABEL[tab];
          const on = i === active;
          return (
            <g
              key={tab}
              role="button"
              tabIndex={0}
              aria-label={label}
              className="cursor-pointer outline-none focus:outline-none"
              style={{ outline: "none" }}
              onClick={() => onSelect(i)}
              onMouseDown={(event) => event.preventDefault()}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(i);
                }
              }}
            >
              <path
                d={arc(i)}
                className={
                  on ? "fill-primary stroke-primary" : "fill-card stroke-border"
                }
                strokeWidth={1.5}
              />
              <text
                x={c + tr * Math.cos(mid)}
                y={c + tr * Math.sin(mid)}
                textAnchor="middle"
                dominantBaseline="central"
                transform={`rotate(${i * step} ${c + tr * Math.cos(mid)} ${c + tr * Math.sin(mid)})`}
                className={`font-display text-[9px] font-bold uppercase ${on ? "fill-primary-foreground" : "fill-muted-foreground"}`}
              >
                {label}
              </text>
            </g>
          );
        })}
      </svg>
      <div className="pointer-events-none absolute inset-0 m-auto flex h-[88px] w-[88px] items-center justify-center rounded-full border border-border bg-background px-2 text-center">
        <span className="font-display text-[11px] font-bold uppercase leading-tight text-primary">
          {TAB_LABEL[tabs[active] ?? tabs[0]!]}
        </span>
      </div>
    </div>
  );
}

export function EmployeeApp() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(() => readStaffToken());
  const [profileOpen, setProfileOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const panel = useRef<HTMLDivElement>(null);

  const session = useQuery({
    queryKey: ["staff", "me", token],
    enabled: Boolean(token),
    queryFn: () =>
      staffFetch<Omit<StaffSession, "token" | "token_type" | "expires_at">>(
        "/me",
      ),
    retry: false,
    refetchInterval: 60_000,
  });

  const expired = statusOf(session.error) === 401;
  const previousRole = useRef<string | undefined>(undefined);
  useEffect(() => {
    const role = session.data?.employee.role;
    if (previousRole.current && role && previousRole.current !== role) {
      void queryClient.cancelQueries({ queryKey: ["staff"] });
      queryClient.removeQueries({
        predicate: (query) =>
          query.queryKey[0] === "staff" && query.queryKey[1] !== "me",
      });
      setProgress(0);
      panel.current?.scrollTo({ top: 0 });
    }
    previousRole.current = role;
  }, [session.data?.employee.role, queryClient]);
  const tabs = session.data?.tabs ?? [];
  const tabKey = tabs.join("|");
  const activeTab =
    tabs[Math.min(tabs.length - 1, Math.max(0, Math.round(progress)))] ??
    "home";
  const [bessie, setBessie] = useState<{
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }>({
    featureId: "staff.benefits",
    hint: "Ask about benefits, or open a file so Bessie can use that evidence.",
  });

  useEffect(() => {
    const el = panel.current;
    if (!el) return;
    const onScroll = () => setProgress(el.scrollTop / el.clientHeight);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [token, tabKey]);

  const goTo = useCallback((index: number) => {
    const el = panel.current;
    if (!el) return;
    el.scrollTo({ top: index * el.clientHeight, behavior: "smooth" });
  }, []);

  const signOut = useCallback(async () => {
    const current = readStaffToken();
    if (current) {
      await staffFetch("/session", { method: "DELETE", token: current }).catch(
        () => undefined,
      );
    }
    writeStaffToken(null);
    writeCustomerSession(null);
    setToken(null);
    setProgress(0);
    queryClient.removeQueries({ queryKey: ["staff"] });
    void navigate({ to: "/login", replace: true });
  }, [queryClient, navigate]);

  useEffect(() => {
    if (!token || expired) {
      writeStaffToken(null);
      writeCustomerSession(null);
      queryClient.removeQueries({ queryKey: ["staff"] });
      void navigate({ to: "/login", replace: true });
    }
    if (statusOf(session.error) === 403)
      void navigate({ to: "/", replace: true });
  }, [token, expired, session.error, queryClient, navigate]);
  if (!token || expired) return <p className="p-8">Returning to sign in…</p>;

  const employee = session.data?.employee;
  const role = employee
    ? (ROLE_LABEL[employee.role] ?? employee.role)
    : "Employee";

  return (
    <div className="employee-ui flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader
        badge="Prototype data"
        role={role}
        onProfile={() => setProfileOpen(true)}
      />
      {session.data && (
        <p className="mb-3 text-xs text-muted-foreground">
          {session.data.banner}
        </p>
      )}
      <div className="relative flex min-h-0 flex-1 overflow-hidden rounded-[2rem] border border-border">
        <div className="relative min-w-0 flex-1">
          <div
            ref={panel}
            className="no-scrollbar h-full overflow-y-auto snap-y snap-mandatory"
          >
            {session.isLoading && (
              <p className="p-10 text-sm text-muted-foreground">
                Loading your desk…
              </p>
            )}
            {session.error && !expired && (
              <p className="p-10 text-sm text-destructive">
                {messageOf(session.error)}
              </p>
            )}
            {session.data &&
              tabs.map((tab, index) => (
                <section key={tab} className="flex h-full snap-start flex-col overflow-y-auto px-6 pb-8 md:pl-72 md:pr-6">
                  <p className="sticky top-0 z-20 -mx-6 mb-4 border-b border-border/70 bg-background/95 px-6 py-3 font-sans text-sm font-semibold tracking-wide text-foreground backdrop-blur md:-ml-72 md:pl-72">
                    {String(index + 1).padStart(2, "0")} — {TAB_LABEL[tab]}
                  </p>
                  {tab === "home" && (
                    <HomePanel
                      banner={session.data.banner}
                      features={session.data.features}
                      onOpen={(next) => goTo(tabs.indexOf(next))}
                    />
                  )}
                  {tab === "research" && (
                    <ResearchPanel
                      focused={activeTab === "research"}
                      onContext={setBessie}
                    />
                  )}
                  {tab === "cases" && (
                    <CasesPanel
                      focused={activeTab === "cases"}
                      onContext={setBessie}
                    />
                  )}
                  {tab === "portfolio" && (
                    <PortfolioPanel
                      features={session.data.features}
                      focused={activeTab === "portfolio"}
                      onContext={setBessie}
                    />
                  )}
                  {tab === "compliance" && (
                    <CompliancePanel
                      features={session.data.features}
                      onOpen={(next) => goTo(tabs.indexOf(next))}
                    />
                  )}
                  {tab === "benefits" && (
                    <BenefitsPanel
                      admin={employee?.role === "benefits_admin"}
                      focused={
                        activeTab === "benefits" ||
                        activeTab === "home" ||
                        activeTab === "activity"
                      }
                      onContext={setBessie}
                    />
                  )}
                  {tab === "learn" && (
                    <div className="max-w-2xl space-y-4">
                      <h1 className="font-display text-4xl font-extrabold">
                        Explain this.
                      </h1>
                      <p className="text-muted-foreground">
                        Ask about a term, policy rule or benefit formula using
                        the permitted evidence from your workspace.
                      </p>
                      <BessieRail
                        featureId="learn.explain"
                        resourceId={
                          bessie.resourceId?.startsWith("RUN-")
                            ? bessie.resourceId
                            : undefined
                        }
                        hint="Your role permissions apply to every explanation."
                      />
                    </div>
                  )}
                </section>
              ))}
          </div>
          {tabs.length > 0 && (
            <div className="absolute -bottom-2 -left-2 z-10">
              <EmployeeWheel tabs={tabs} progress={progress} onSelect={goTo} />
            </div>
          )}
        </div>
        <div className="hidden lg:block">
          <BessieRail
            key={`${token}:${employee?.role}:${activeTab}:${bessie.resourceId ?? ""}`}
            featureId={
              activeTab === "compliance"
                ? session.data?.features.includes("staff.fairness")
                  ? "staff.fairness"
                  : "staff.audit"
                : activeTab === "learn"
                  ? "learn.explain"
                  : activeTab === "research" ||
                      activeTab === "cases" ||
                      activeTab === "portfolio"
                    ? bessie.featureId
                    : "staff.benefits"
            }
            resourceId={
              activeTab === "research" || activeTab === "cases"
                ? bessie.resourceId
                : undefined
            }
            hint={bessie.hint}
          />
        </div>
      </div>
      {profileOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4"
          role="dialog"
          aria-modal="true"
          aria-label="Profile"
        >
          <div className="w-full max-w-md space-y-4 rounded-2xl border border-border bg-background p-6">
            <h2 className="font-sans text-2xl font-semibold">{employee?.display_name}</h2>
            <p>{role}</p>
            <p className="text-sm text-muted-foreground">Workspace access is assigned to your account.</p>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setProfileOpen(false)}>Close</Button>
              <Button onClick={() => void signOut()}>Sign out</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function HomePanel({
  banner,
  features,
  onOpen,
}: {
  banner: string;
  features: string[];
  onOpen: (tab: StaffTab) => void;
}) {
  const home = useQuery({
    queryKey: ["staff", "home"],
    queryFn: () =>
      staffFetch<{
        greeting: string;
        role: string;
        counts: Record<string, number>;
        banner: string;
      }>("/home"),
  });
  const workspace: StaffTab = features.includes("staff.creditresearch")
    ? "research"
    : features.includes("staff.cases")
      ? "cases"
      : features.includes("staff.portfolio")
        ? "portfolio"
        : features.includes("staff.audit")
          ? "compliance"
          : "benefits";
  const counts = home.data?.counts ?? {};
  return (
    <div className="max-w-3xl space-y-4">
      <PanelState loading={home.isLoading} error={home.error}>
        <h1 className="font-display text-4xl font-extrabold leading-[0.95] md:text-5xl">
          {home.data?.greeting}
        </h1>
        <p className="text-muted-foreground">
          {ROLE_LABEL[home.data?.role ?? ""] ?? home.data?.role}
        </p>
        <QuickActions
          items={[
            {
              label: "Open your queue",
              detail:
                Object.entries(counts)
                  .map(([key, value]) => `${value} ${key.replaceAll("_", " ")}`)
                  .join(" · ") || "Go to the work assigned to this role",
              onClick: () => onOpen(workspace),
            },
            {
              label: "Check benefits",
              detail:
                "Tenure discount, remaining cap, and a simulated redemption",
              onClick: () => onOpen("benefits"),
            },
            {
              label: "Review activity",
              detail:
                "Your decisions, case notes, and redemptions on this desk",
              onClick: () => onOpen("activity"),
            },
            {
              label: "Ask Bessie",
              detail:
                "She stays on the right. Open a file first if you want file evidence.",
              onClick: () => onOpen(workspace),
            },
          ]}
        />
      </PanelState>
      <p className="text-xs text-muted-foreground">{banner}</p>
    </div>
  );
}

function ResearchPanel({
  focused,
  onContext,
}: {
  focused: boolean;
  onContext: (next: {
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }) => void;
}) {
  const queue = useQuery({
    queryKey: ["staff", "prospects"],
    queryFn: () =>
      staffFetch<{
        prospects: { id: string; product: string; application_ref: string }[];
        blind_review: boolean;
      }>("/prospects"),
  });
  const [prospectId, setProspectId] = useState<string | null>(null);
  const [purpose, setPurpose] = useState("");
  const [reference, setReference] = useState("");
  const [breakGlass, setBreakGlass] = useState("");
  const [grantId, setGrantId] = useState<string | null>(null);
  const [run, setRun] = useState<Record<string, unknown> | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [overrideReason, setOverrideReason] = useState("");
  const [recorded, setRecorded] = useState<string | null>(null);
  const prospect = queue.data?.prospects.find((row) => row.id === prospectId);
  useEffect(() => {
    if (!focused) return;
    onContext({
      featureId:
        typeof run?.["id"] === "string"
          ? "staff.creditresearch"
          : "staff.benefits",
      resourceId: typeof run?.["id"] === "string" ? run["id"] : undefined,
      hint:
        typeof run?.["id"] === "string"
          ? "Bessie can explain this research run."
          : "Open a file before asking about its evidence.",
    });
  }, [focused, onContext, run]);

  const openGrant = async () => {
    if (!prospect || !purpose) return;
    setBusy("grant");
    setError(null);
    setRun(null);
    setDecision("");
    setRecorded(null);
    try {
      const grant = await staffFetch<{ id: string }>("/access-grants", {
        body: {
          prospect_id: prospect.id,
          purpose,
          reference_id: reference || prospect.application_ref,
          ...(breakGlass.trim()
            ? { break_glass_reason: breakGlass.trim() }
            : {}),
        },
      });
      setGrantId(grant.id);
      const profile = await staffFetch<{ prospect: Record<string, unknown> }>(
        `/prospects/${prospect.id}?grant_id=${grant.id}`,
      );
      const result = await staffFetch<Record<string, unknown>>(
        "/research-runs",
        { body: { grant_id: grant.id } },
      );
      setRun({ ...result, profile: profile.prospect });
    } catch (err) {
      setError(err);
    } finally {
      setBusy(null);
    }
  };

  const rules =
    (run?.["rules"] as
      | { rule: string; value: unknown; status: string; reason_code?: string }[]
      | undefined) ?? [];
  const recommended = String(run?.["recommended_human_action"] ?? "");
  const needsOverride = Boolean(decision) && decision !== recommended;

  const chooseProspect = (id: string) => {
    const row = queue.data?.prospects.find((item) => item.id === id);
    setProspectId(id || null);
    setReference(row?.application_ref ?? "");
    setGrantId(null);
    setRun(null);
    setDecision("");
    setRationale("");
    setOverrideReason("");
    setRecorded(null);
    setPurpose("");
  };

  return (
    <div className="max-w-5xl space-y-4">
      <h1 className="font-display text-4xl font-extrabold">
        Review with a clearer view.
      </h1>
      <label className="block max-w-md text-sm">
        Assigned queue
        <select
          className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 outline-none"
          aria-label="Assigned queue"
          value={prospectId ?? ""}
          onChange={(event) => chooseProspect(event.target.value)}
        >
          <option value="">
            {queue.isLoading ? "Loading queue…" : "Select an application"}
          </option>
          {queue.data?.prospects.map((row) => (
            <option key={row.id} value={row.id}>
              {row.id} · {row.product}
            </option>
          ))}
        </select>
      </label>
      {queue.error ? (
        <p className="text-sm text-destructive">{messageOf(queue.error)}</p>
      ) : null}
      {!queue.isLoading && queue.data && queue.data.prospects.length === 0 && (
        <p className="text-sm text-muted-foreground">
          Nothing is assigned yet.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Blind review. Name, age and location stay hidden.
      </p>
      <QuickActions
        items={[
          {
            label: "Next assigned file",
            detail: queue.data?.prospects[0]
              ? `${queue.data.prospects[0].id} · ${queue.data.prospects[0].product}`
              : "Queue is empty",
            onClick: () => {
              const next = queue.data?.prospects[0];
              if (!next) return;
              setProspectId(next.id);
              setReference(next.application_ref);
              setPurpose("application_review");
              setRun(null);
              setDecision("");
            },
          },
          {
            label: "Application review",
            detail: prospect
              ? `Purpose ready for ${prospect.id}`
              : "Select a prospect, then confirm the reference",
            onClick: () => setPurpose("application_review"),
          },
          {
            label: "Senior review",
            detail:
              "Sets the purpose. You still confirm the reference and the decision.",
            onClick: () => setPurpose("senior_review"),
          },
          {
            label: "Refresh queue",
            detail: "Reload the assigned prospects",
            onClick: () => void queue.refetch(),
          },
        ]}
      />
      {!prospect && (
        <p className="text-sm text-muted-foreground">
          Select a prospect from the queue.
        </p>
      )}
      {prospect && !run && (
        <div className="space-y-3 rounded-2xl border border-border p-4">
          <p className="font-display font-bold">
            {prospect.id} · {prospect.product}
          </p>
          <label className="block text-sm">
            Purpose
            <select
              className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2"
              value={purpose}
              onChange={(event) => setPurpose(event.target.value)}
            >
              <option value="">Select a purpose</option>
              <option value="application_review">Application review</option>
              <option value="senior_review">Senior review</option>
              <option value="quality_review">Quality review</option>
            </select>
          </label>
          <label className="block text-sm">
            Application reference
            <Input
              className="mt-1"
              value={reference}
              onChange={(event) => setReference(event.target.value)}
            />
          </label>
          <label className="block text-sm">
            Break-glass reason
            <Input
              className="mt-1"
              value={breakGlass}
              onChange={(event) => setBreakGlass(event.target.value)}
              placeholder="Only if this file is outside your assignment"
            />
          </label>
          <Button
            disabled={!purpose || busy !== null}
            onClick={() => void openGrant()}
          >
            {busy === "grant" ? "Opening…" : "Open research"}
          </Button>
          {error ? (
            <p className="text-sm text-destructive">{messageOf(error)}</p>
          ) : null}
        </div>
      )}
      {run && (
        <>
          <p className="text-sm text-muted-foreground">
            Outcome {String(run["outcome"])} · policy{" "}
            {String(run["policy_version"])}
          </p>
          <p className="text-sm">
            Suggested next step: {recommended}. Choose your own decision below.
          </p>
          <div className="overflow-x-auto rounded-2xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Rule</th>
                  <th className="px-3 py-2">Value</th>
                  <th className="px-3 py-2">Result</th>
                </tr>
              </thead>
              <tbody>
                {rules.map((rule) => (
                  <tr key={rule.rule} className="border-t border-border">
                    <td className="px-3 py-2">{rule.rule}</td>
                    <td className="px-3 py-2">{String(rule.value)}</td>
                    <td className="px-3 py-2">{rule.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-3 md:grid-cols-3">
            <article className="rounded-2xl border border-border p-3 text-sm">
              <h3 className="font-display font-bold">Strengths</h3>
              <p>
                {((run["strengths"] as string[]) ?? []).join(", ") ||
                  "None listed."}
              </p>
              <h3 className="mt-2 font-display font-bold">Concerns</h3>
              <p>
                {((run["concerns"] as string[]) ?? []).join(", ") ||
                  "None listed."}
              </p>
            </article>
            <article className="rounded-2xl border border-border p-3 text-sm">
              <h3 className="font-display font-bold">Missing inputs</h3>
              <p>
                {((run["missing_inputs"] as string[]) ?? []).join(", ") ||
                  "None required."}
              </p>
            </article>
            <article className="rounded-2xl border border-border p-3 text-sm">
              <h3 className="font-display font-bold">
                What would change the outcome?
              </h3>
              {(
                (run["counterfactuals"] as {
                  changes: Record<string, number>;
                  verified_outcome: string;
                }[]) ?? []
              ).length === 0 && (
                <p>No supported numerical improvement was found.</p>
              )}
              {(
                (run["counterfactuals"] as {
                  changes: Record<string, number>;
                  verified_outcome: string;
                }[]) ?? []
              ).map((item, index) => (
                <p key={index}>
                  {JSON.stringify(item.changes)} → {item.verified_outcome}
                </p>
              ))}
              <p className="mt-2 text-xs text-muted-foreground">
                {String(
                  (
                    run["indicative_pricing"] as
                      { apr_percent?: number; label?: string } | undefined
                  )?.apr_percent ?? "",
                )}
                %{" "}
                {
                  (run["indicative_pricing"] as { label?: string } | undefined)
                    ?.label
                }
              </p>
            </article>
          </div>
          <div className="space-y-2 rounded-2xl border border-border p-4">
            <h3 className="font-display font-bold">Your decision</h3>
            <p className="text-sm text-muted-foreground">
              Nothing is sent externally. A different choice than the suggestion
              needs an override reason.
            </p>
            <select
              className="w-full rounded-md border border-border bg-background px-3 py-2"
              value={decision}
              onChange={(event) => setDecision(event.target.value)}
              aria-label="Select a decision"
            >
              <option value="">Select a decision</option>
              {DECISIONS.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <Textarea
              value={rationale}
              onChange={(event) => setRationale(event.target.value)}
              placeholder="Rationale (at least 10 characters)"
            />
            {needsOverride && (
              <Textarea
                value={overrideReason}
                onChange={(event) => setOverrideReason(event.target.value)}
                placeholder="Override reason (at least 10 characters)"
              />
            )}
            <Button
              disabled={
                !decision ||
                rationale.trim().length < 10 ||
                (needsOverride && overrideReason.trim().length < 10) ||
                busy !== null
              }
              onClick={() => {
                setBusy("decision");
                setError(null);
                void staffFetch<{ id: string }>("/decisions", {
                  body: {
                    run_id: run["id"],
                    decision,
                    rationale: rationale.trim(),
                    ...(needsOverride
                      ? { override_reason: overrideReason.trim() }
                      : {}),
                  },
                })
                  .then((row) => setRecorded(row.id))
                  .catch((err) => setError(err))
                  .finally(() => setBusy(null));
              }}
            >
              Record simulated decision
            </Button>
            {recorded && (
              <p className="text-sm text-primary">Recorded {recorded}.</p>
            )}
            {error ? (
              <p className="text-sm text-destructive">{messageOf(error)}</p>
            ) : null}
            {grantId && (
              <p className="text-xs text-muted-foreground">
                Grant {grantId} covers this file for a short window.
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function CasesPanel({
  focused,
  onContext,
}: {
  focused: boolean;
  onContext: (next: {
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }) => void;
}) {
  const cases = useQuery({
    queryKey: ["staff", "cases"],
    queryFn: () =>
      staffFetch<{
        cases: { id: string; status: string; consented_context: string }[];
      }>("/cases"),
  });
  const [caseId, setCaseId] = useState<string | null>(null);
  const detail = useQuery({
    queryKey: ["staff", "case", caseId],
    enabled: Boolean(caseId),
    queryFn: () =>
      staffFetch<{
        case: { id: string; status: string };
        brief: { situation: string; provider: string };
        events: { id: string; note: string; status: string }[];
      }>(`/cases/${caseId}`),
  });
  const [status, setStatus] = useState("in_progress");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  useEffect(() => {
    if (!focused) return;
    onContext({
      featureId: caseId ? "staff.cases" : "staff.benefits",
      resourceId: caseId ?? undefined,
      hint: caseId
        ? "Bessie can use this case’s consented context."
        : "Open a case before asking about it.",
    });
  }, [caseId, focused, onContext]);
  const openCases = (cases.data?.cases ?? []).filter(
    (row) => row.status !== "resolved",
  );
  return (
    <div className="grid max-w-4xl gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
      <PanelState
        loading={cases.isLoading}
        error={cases.error}
        empty={!cases.data?.cases.length}
      >
        <ul className="space-y-2">
          {cases.data?.cases.map((row) => (
            <li key={row.id}>
              <button
                type="button"
                className="w-full rounded-2xl border border-border px-3 py-2 text-left"
                onClick={() => setCaseId(row.id)}
              >
                <span className="font-display font-bold">{row.id}</span>
                <span className="block text-xs text-muted-foreground">
                  {row.status}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PanelState>
      <div className="space-y-3">
        <h1 className="font-display text-4xl font-extrabold">Cases</h1>
        <QuickActions
          items={[
            {
              label: "Oldest open case",
              detail: openCases[0]
                ? `${openCases[0].id} · ${openCases[0].status}`
                : "No open cases",
              onClick: () => openCases[0] && setCaseId(openCases[0].id),
            },
            {
              label: "Mark in progress",
              detail: "Fills the status. Add a note before you save.",
              onClick: () => setStatus("in_progress"),
            },
            {
              label: "Mark resolved",
              detail: "Resolved cases cannot be reopened.",
              onClick: () => setStatus("resolved"),
            },
            {
              label: "Refresh queue",
              detail: "Reload assigned handoffs",
              onClick: () => void cases.refetch(),
            },
          ]}
        />
        <PanelState
          loading={Boolean(caseId) && detail.isLoading}
          error={detail.error}
        >
          {detail.data && (
            <>
              <p className="text-sm">{detail.data.brief.situation}</p>
              <p className="text-xs text-muted-foreground">
                Brief provider: {detail.data.brief.provider}
              </p>
              <ul className="text-sm text-muted-foreground">
                {detail.data.events.map((event) => (
                  <li key={event.id}>
                    {event.status}: {event.note}
                  </li>
                ))}
              </ul>
              <select
                className="rounded-md border border-border bg-background px-3 py-2"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
              >
                <option value="assigned">assigned</option>
                <option value="in_progress">in_progress</option>
                <option value="resolved">resolved</option>
              </select>
              <Input
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Note"
              />
              <Button
                onClick={() => {
                  setError(null);
                  void staffFetch(`/cases/${caseId}`, {
                    method: "PATCH",
                    body: { status, note },
                  })
                    .then(() => {
                      setNote("");
                      void queryClient.invalidateQueries({
                        queryKey: ["staff", "case", caseId],
                      });
                      void queryClient.invalidateQueries({
                        queryKey: ["staff", "cases"],
                      });
                    })
                    .catch((err) => setError(messageOf(err)));
                }}
              >
                Update case
              </Button>
              {error && <p className="text-sm text-destructive">{error}</p>}
            </>
          )}
        </PanelState>
      </div>
    </div>
  );
}

function PortfolioPanel({
  features,
  focused,
  onContext,
}: {
  features: string[];
  focused: boolean;
  onContext: (next: {
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }) => void;
}) {
  const portfolio = useQuery({
    queryKey: ["staff", "portfolio"],
    queryFn: () => staffFetch<Record<string, unknown>>("/portfolio"),
  });
  useEffect(() => {
    if (!focused) return;
    onContext({
      featureId: "staff.portfolio",
      hint: "Bessie summarizes the aggregates allowed for this role.",
    });
  }, [focused, onContext]);
  const audience = useQuery({
    queryKey: ["staff", "audience"],
    enabled: features.includes("staff.campaigns"),
    queryFn: () =>
      staffFetch<{ status: string; message: string; audience: unknown[] }>(
        "/campaigns/audience",
      ),
  });
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="font-display text-4xl font-extrabold">Portfolio</h1>
      <QuickActions
        items={[
          {
            label: "Refresh aggregates",
            detail: "Reload the local finance snapshot",
            onClick: () => void portfolio.refetch(),
          },
          ...(features.includes("staff.campaigns")
            ? [
                {
                  label: "Check audience",
                  detail:
                    "Shows the unavailable consent state. Nothing is sent.",
                  onClick: () => void audience.refetch(),
                },
              ]
            : []),
        ]}
      />
      <PanelState loading={portfolio.isLoading} error={portfolio.error}>
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border p-4 text-xs">
          {JSON.stringify(portfolio.data, null, 2)}
        </pre>
      </PanelState>
      {features.includes("staff.campaigns") && (
        <PanelState loading={audience.isLoading} error={audience.error}>
          <article className="rounded-2xl border border-border p-4 text-sm">
            <p className="font-display font-bold">Campaign audience</p>
            <p>{audience.data?.message}</p>
            <p className="text-xs text-muted-foreground">
              Status: {audience.data?.status}
            </p>
          </article>
        </PanelState>
      )}
    </div>
  );
}

function CompliancePanel({
  features,
  onOpen,
}: {
  features: string[];
  onOpen: (tab: StaffTab) => void;
}) {
  const reviews = useQuery({
    queryKey: ["staff", "reviews"],
    enabled: features.includes("staff.decision"),
    queryFn: () => staffFetch<Record<string, unknown>>("/compliance/reviews"),
  });
  const audit = useQuery({
    queryKey: ["staff", "audit"],
    enabled: features.includes("staff.audit"),
    queryFn: () =>
      staffFetch<{
        events: { id?: string; action: string; outcome: string; ts: string }[];
      }>("/audit?limit=25"),
  });
  const fairness = useQuery({
    queryKey: ["staff", "fairness"],
    enabled: features.includes("staff.fairness"),
    queryFn: () => staffFetch<Record<string, unknown>>("/compliance/fairness"),
  });
  const anomalies = useQuery({
    queryKey: ["staff", "anomalies"],
    enabled: features.includes("staff.anomaly"),
    queryFn: () =>
      staffFetch<{ status: string; message: string; anomalies: unknown[] }>(
        "/compliance/anomalies",
      ),
  });
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="font-display text-4xl font-extrabold">Compliance</h1>
      <QuickActions
        items={[
          ...(features.includes("staff.audit")
            ? [
                {
                  label: "Latest audit",
                  detail: "Reload the newest recorded events",
                  onClick: () => void audit.refetch(),
                },
              ]
            : []),
          ...(features.includes("staff.decision")
            ? [
                {
                  label: "Override queue",
                  detail: "Reload decisions that need review",
                  onClick: () => void reviews.refetch(),
                },
              ]
            : []),
          ...(features.includes("staff.fairness")
            ? [
                {
                  label: "Fairness check",
                  detail: "Reload recorded-run metrics",
                  onClick: () => void fairness.refetch(),
                },
              ]
            : []),
          {
            label: "Your activity",
            detail: "Decisions and redemptions recorded for you",
            onClick: () => onOpen("activity"),
          },
        ]}
      />
      {features.includes("staff.anomaly") && (
        <PanelState loading={anomalies.isLoading} error={anomalies.error}>
          <article className="rounded-2xl border border-border p-4 text-sm">
            <p className="font-display font-bold">Anomalies</p>
            <p>{anomalies.data?.message}</p>
            <p className="text-xs text-muted-foreground">
              {anomalies.data?.status}
            </p>
          </article>
        </PanelState>
      )}
      {features.includes("staff.decision") && (
        <PanelState
          loading={reviews.isLoading}
          error={reviews.error}
          empty={
            Array.isArray(reviews.data?.["overrides"]) &&
            (reviews.data?.["overrides"] as unknown[]).length === 0
          }
        >
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border p-4 text-xs">
            {JSON.stringify(reviews.data, null, 2)}
          </pre>
        </PanelState>
      )}
      {features.includes("staff.fairness") && (
        <PanelState loading={fairness.isLoading} error={fairness.error}>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-2xl border border-border p-4 text-xs">
            {JSON.stringify(fairness.data, null, 2)}
          </pre>
        </PanelState>
      )}
      {features.includes("staff.audit") && (
        <PanelState
          loading={audit.isLoading}
          error={audit.error}
          empty={!audit.data?.events.length}
        >
          <ul className="space-y-1 text-sm">
            {audit.data?.events.map((event, index) => (
              <li
                key={event.id ?? index}
                className="rounded-xl border border-border px-3 py-2"
              >
                {event.action} · {event.outcome}
              </li>
            ))}
          </ul>
        </PanelState>
      )}
    </div>
  );
}

function BenefitsPanel({
  admin,
  focused,
  onContext,
}: {
  admin: boolean;
  focused: boolean;
  onContext: (next: {
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }) => void;
}) {
  const benefits = useQuery({
    queryKey: ["staff", "benefits"],
    queryFn: () =>
      staffFetch<{
        tenure_months: number;
        discount_rate_percent: number;
        remaining_cap_cents: number;
        catalog: { item_key: string; name: string; list_price_cents: number }[];
        redemption_label: string;
        ledger: { id: string; item_key: string; discount_cents: number }[];
      }>("/benefits"),
  });
  const usage = useQuery({
    queryKey: ["staff", "benefits-usage"],
    enabled: admin,
    queryFn: () =>
      staffFetch<{ redemptions: number; discount_cents: number }>(
        "/benefits/admin/usage",
      ),
  });
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [cap, setCap] = useState("50000");
  const dollars = (cents: number) => `$${(cents / 100).toFixed(2)}`;
  useEffect(() => {
    if (!focused) return;
    onContext({
      featureId: "staff.benefits",
      hint: "Bessie explains the tenure discount, cap, and item limit.",
    });
  }, [focused, onContext]);
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="font-display text-4xl font-extrabold">Benefits</h1>
      <QuickActions
        items={[
          {
            label: "Redeem first catalog item",
            detail: benefits.data?.catalog[0]
              ? benefits.data.catalog[0].name
              : "Catalog is still loading",
            onClick: () => {
              const item = benefits.data?.catalog[0];
              if (!item) return;
              setError(null);
              void staffFetch("/benefits/redemptions", {
                body: {
                  item_id: item.item_key,
                  quantity: 1,
                  request_id: crypto.randomUUID(),
                },
              })
                .then(() =>
                  queryClient.invalidateQueries({
                    queryKey: ["staff", "benefits"],
                  }),
                )
                .catch((err) => setError(messageOf(err)));
            },
          },
          {
            label: "Refresh benefits",
            detail: "Reload cap, catalog, and your ledger",
            onClick: () => void benefits.refetch(),
          },
        ]}
      />
      <PanelState loading={benefits.isLoading} error={benefits.error}>
        {benefits.data && (
          <>
            <p className="text-sm text-muted-foreground">
              {benefits.data.tenure_months} months ·{" "}
              {benefits.data.discount_rate_percent}% discount ·{" "}
              {dollars(benefits.data.remaining_cap_cents)} cap left
            </p>
            <p className="text-xs text-muted-foreground">
              {benefits.data.redemption_label}
            </p>
            <ul className="space-y-2">
              {benefits.data.catalog.map((item) => (
                <li
                  key={item.item_key}
                  className="flex items-center justify-between rounded-2xl border border-border px-3 py-2 text-sm"
                >
                  <span>
                    {item.name} · {dollars(item.list_price_cents)}
                  </span>
                  <Button
                    size="sm"
                    onClick={() => {
                      setError(null);
                      void staffFetch("/benefits/redemptions", {
                        body: {
                          item_id: item.item_key,
                          quantity: 1,
                          request_id: crypto.randomUUID(),
                        },
                      })
                        .then(() =>
                          queryClient.invalidateQueries({
                            queryKey: ["staff", "benefits"],
                          }),
                        )
                        .catch((err) => setError(messageOf(err)));
                    }}
                  >
                    Redeem
                  </Button>
                </li>
              ))}
            </ul>
            <ul className="text-sm text-muted-foreground">
              {benefits.data.ledger.map((row) => (
                <li key={row.id}>
                  {row.item_key} saved {dollars(row.discount_cents)}
                </li>
              ))}
            </ul>
          </>
        )}
      </PanelState>
      {error && <p className="text-sm text-destructive">{error}</p>}
      {admin && (
        <div className="space-y-3 rounded-2xl border border-border p-4">
          <h2 className="font-display font-bold">Admin controls</h2>
          <PanelState loading={usage.isLoading} error={usage.error}>
            <p className="text-sm">
              {usage.data?.redemptions} redemptions ·{" "}
              {dollars(usage.data?.discount_cents ?? 0)} discounts
            </p>
          </PanelState>
          <label className="block text-sm">
            New annual cap (cents)
            <Input
              className="mt-1"
              value={cap}
              onChange={(event) => setCap(event.target.value)}
            />
          </label>
          <Button
            onClick={() => {
              setError(null);
              void staffFetch("/benefits/admin/rules", {
                body: {
                  annual_cap_cents: Number(cap),
                  quarterly_item_limit: 2,
                  rates: [10, 15, 20],
                },
              })
                .then(() =>
                  queryClient.invalidateQueries({
                    queryKey: ["staff", "benefits"],
                  }),
                )
                .catch((err) => setError(messageOf(err)));
            }}
          >
            Publish rules version
          </Button>
        </div>
      )}
    </div>
  );
}

function ActivityPanel({ features }: { features: string[] }) {
  const decisions = useQuery({
    queryKey: ["staff", "decisions"],
    enabled: features.includes("staff.decision"),
    queryFn: () =>
      staffFetch<{
        decisions: {
          id: string;
          decision: string;
          rationale: string;
          recorded_at?: string;
          override?: boolean;
        }[];
      }>("/decisions"),
  });
  const benefits = useQuery({
    queryKey: ["staff", "benefits"],
    queryFn: () =>
      staffFetch<{
        ledger: {
          id: string;
          item_key: string;
          discount_cents: number;
          redeemed_at?: string;
          label?: string;
        }[];
      }>("/benefits"),
  });
  const cases = useQuery({
    queryKey: ["staff", "cases"],
    enabled: features.includes("staff.cases"),
    queryFn: () =>
      staffFetch<{
        cases: { id: string; status: string; consented_context: string }[];
      }>("/cases"),
  });
  const rows = [
    ...(decisions.data?.decisions ?? []).map((row) => ({
      id: row.id,
      title: row.decision,
      detail: row.rationale,
      when: row.recorded_at ?? "",
    })),
    ...(benefits.data?.ledger ?? []).map((row) => ({
      id: row.id,
      title: `Redeemed ${row.item_key}`,
      detail:
        row.label ??
        `Saved $${(row.discount_cents / 100).toFixed(2)}. Simulated redemption.`,
      when: row.redeemed_at ?? "",
    })),
    ...(cases.data?.cases ?? []).map((row) => ({
      id: row.id,
      title: `Case ${row.id} · ${row.status}`,
      detail: row.consented_context,
      when: "",
    })),
  ].sort((a, b) => b.when.localeCompare(a.when));
  const canDecisions = features.includes("staff.decision");
  const canCases = features.includes("staff.cases");
  const loading =
    (canDecisions && decisions.isLoading) ||
    benefits.isLoading ||
    (canCases && cases.isLoading);
  const error =
    (canDecisions ? decisions.error : null) ??
    benefits.error ??
    (canCases ? cases.error : null);
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="font-display text-4xl font-extrabold">Your activity</h1>
      <QuickActions
        items={[
          {
            label: "Refresh record",
            detail: "Reload the records this role is allowed to see",
            onClick: () => {
              if (canDecisions) void decisions.refetch();
              void benefits.refetch();
              if (canCases) void cases.refetch();
            },
          },
        ]}
      />
      <PanelState
        loading={loading}
        error={error}
        empty={!loading && rows.length === 0}
      >
        <ul className="space-y-2">
          {rows.map((row) => (
            <li
              key={row.id}
              className="rounded-2xl border border-border px-4 py-3"
            >
              <p className="font-display font-bold">{row.title}</p>
              <p className="text-sm text-muted-foreground">{row.detail}</p>
              {row.when && (
                <p className="mt-1 text-xs text-muted-foreground">{row.when}</p>
              )}
            </li>
          ))}
        </ul>
      </PanelState>
    </div>
  );
}
