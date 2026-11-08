import { useMemo, useState } from "react";
import { ArrowRight, Check, ChevronRight, Lock, TriangleAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type Product = "Credit card" | "Personal loan";
type Result = "Pass" | "Watch";

type Prospect = {
  id: string;
  product: Product;
  headline: string;
  summary: string;
  asOf: string;
  refer: boolean;
  rules: { rule: string; value: string; target: string; result: Result }[];
  strengths: string;
  missing: string;
  change: { amount: string; detail: string; scenario: string; apr: string };
};

const PROSPECTS: Prospect[] = [
  {
    id: "P-DEMO-09",
    product: "Credit card",
    headline: "Needs senior review",
    summary: "Utilization exceeds the synthetic policy target.",
    asOf: "Nov 7, 2026",
    refer: true,
    rules: [
      { rule: "Credit band", value: "Good", target: "Good or Excellent", result: "Pass" },
      { rule: "Utilization", value: "32%", target: "≤30%", result: "Watch" },
      { rule: "Debt-to-income", value: "9.75%", target: "≤36%", result: "Pass" },
      { rule: "Delinquencies (24 mo)", value: "0", target: "0", result: "Pass" },
      { rule: "Credit history", value: "48 mo", target: "≥24 mo", result: "Pass" },
      { rule: "Inquiries (6 mo)", value: "1", target: "≤2", result: "Pass" },
      { rule: "Requested limit / income", value: "6.25%", target: "≤25%", result: "Pass" },
      { rule: "Income verification", value: "Verified", target: "Required", result: "Pass" },
    ],
    strengths: "Verified income and established history. Utilization is above the target.",
    missing: "None required for this evaluation.",
    change: {
      amount: "$400 lower revolving balance",
      detail: "From $6,400 to $6,000 brings utilization to 30%.",
      scenario: "MEETS_POLICY",
      apr: "22% indicative APR",
    },
  },
  {
    id: "P-DEMO-11",
    product: "Personal loan",
    headline: "Within the synthetic target",
    summary: "Debt-to-income and payment history both clear the sample rules.",
    asOf: "Nov 7, 2026",
    refer: false,
    rules: [
      { rule: "Credit band", value: "Excellent", target: "Good or Excellent", result: "Pass" },
      { rule: "Debt-to-income", value: "18%", target: "≤36%", result: "Pass" },
      { rule: "Delinquencies (24 mo)", value: "0", target: "0", result: "Pass" },
      { rule: "Requested payment / income", value: "8%", target: "≤15%", result: "Pass" },
      { rule: "Income verification", value: "Verified", target: "Required", result: "Pass" },
    ],
    strengths: "Stable verified income and no recent delinquencies.",
    missing: "None required for this evaluation.",
    change: {
      amount: "No change required",
      detail: "The sample file already meets every listed rule.",
      scenario: "MEETS_POLICY",
      apr: "11% indicative APR",
    },
  },
  {
    id: "P-DEMO-13",
    product: "Credit card",
    headline: "Needs senior review",
    summary: "Recent inquiries sit above the synthetic cap.",
    asOf: "Nov 7, 2026",
    refer: true,
    rules: [
      { rule: "Credit band", value: "Good", target: "Good or Excellent", result: "Pass" },
      { rule: "Utilization", value: "21%", target: "≤30%", result: "Pass" },
      { rule: "Inquiries (6 mo)", value: "4", target: "≤2", result: "Watch" },
      { rule: "Credit history", value: "30 mo", target: "≥24 mo", result: "Pass" },
      { rule: "Income verification", value: "Verified", target: "Required", result: "Pass" },
    ],
    strengths: "Utilization is inside the target. Inquiry count is not.",
    missing: "None required for this evaluation.",
    change: {
      amount: "Wait out two inquiries",
      detail: "Two of the four inquiries age past six months next quarter.",
      scenario: "MEETS_POLICY",
      apr: "24% indicative APR",
    },
  },
];

type LogEntry = { id: string; prospectId: string; decision: string; rationale: string };

const SESSION_KEY = "finpilot.employee";

export function EmployeeDesk() {
  const [signedIn, setSignedIn] = useState(() =>
    typeof window !== "undefined" ? window.sessionStorage.getItem(SESSION_KEY) === "analyst" : false,
  );
  if (!signedIn) return <EmployeeLogin onEnter={() => setSignedIn(true)} />;
  return <ResearchDesk onSignOut={() => setSignedIn(false)} />;
}

function EmployeeLogin({ onEnter }: { onEnter: () => void }) {
  const [employeeId, setEmployeeId] = useState("analyst");
  const [error, setError] = useState<string | null>(null);
  return (
    <form
      className="mx-auto flex w-full max-w-md flex-col gap-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (employeeId.trim().toLowerCase() !== "analyst") {
          setError("Use the sample id analyst. This desk does not check a real directory.");
          return;
        }
        window.sessionStorage.setItem(SESSION_KEY, "analyst");
        onEnter();
      }}
    >
      <p className="font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
        Employee sign in
      </p>
      <h1 className="font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
        Open the research desk.
      </h1>
      <p className="text-muted-foreground">
        Synthetic demo for a credit analyst. Nothing here is a live credit decision.
      </p>
      <label className="text-sm" htmlFor="employee-id">
        Employee id
        <Input
          id="employee-id"
          className="mt-1"
          value={employeeId}
          onChange={(event) => setEmployeeId(event.target.value)}
          autoComplete="username"
        />
      </label>
      <p className="text-xs text-muted-foreground">Sample id: analyst</p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Button type="submit" className="w-fit">
        Sign in
      </Button>
    </form>
  );
}

function ResearchDesk({ onSignOut }: { onSignOut: () => void }) {
  const [prospectId, setProspectId] = useState(PROSPECTS[0]!.id);
  const [tab, setTab] = useState<"research" | "profiles" | "log">("research");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [decision, setDecision] = useState("");
  const [rationale, setRationale] = useState("");
  const [log, setLog] = useState<LogEntry[]>([]);
  const [blind, setBlind] = useState(true);
  const prospect = PROSPECTS.find((item) => item.id === prospectId) ?? PROSPECTS[0]!;
  const watches = useMemo(
    () => prospect.rules.filter((rule) => rule.result === "Watch"),
    [prospect],
  );

  const ask = () => {
    const text = question.trim().toLowerCase();
    if (!text) return;
    if (text.includes("utilization") || text.includes("review")) {
      setAnswer(
        watches.length
          ? `${prospect.id} is in review because ${watches.map((rule) => `${rule.rule} is ${rule.value} versus ${rule.target}`).join("; ")}. This is a synthetic rule, not a bank policy.`
          : `${prospect.id} has no watch rows under the sample rules.`,
      );
    } else {
      setAnswer(
        "Bessie only answers from the rule table on this screen. Ask about utilization, the review, or a listed rule.",
      );
    }
  };

  return (
    <div className="grid min-h-0 gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside className="space-y-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.2em] text-muted-foreground">
            Assigned queue
          </p>
          <p className="text-sm text-muted-foreground">{PROSPECTS.length} prospects</p>
        </div>
        <ul className="space-y-2">
          {PROSPECTS.map((item) => (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => {
                  setProspectId(item.id);
                  setAnswer(null);
                  setTab("research");
                }}
                className={`flex w-full items-center justify-between rounded-2xl border px-3 py-2 text-left ${
                  item.id === prospect.id ? "border-primary" : "border-border"
                }`}
              >
                <span>
                  <span className="block font-display text-sm font-bold">{item.id}</span>
                  <span className="text-xs text-muted-foreground">{item.product}</span>
                </span>
                <ChevronRight className="size-4 text-primary" aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <button
          type="button"
          onClick={() => setBlind((value) => !value)}
          className="flex items-start gap-2 text-left text-sm text-muted-foreground"
        >
          <Lock className="mt-0.5 size-4 text-primary" aria-hidden="true" />
          <span>
            Blind review {blind ? "on" : "off"}
            <span className="block text-xs">Name, age and location hidden</span>
          </span>
        </button>
        <Button variant="ghost" className="px-0 text-muted-foreground" onClick={() => {
          window.sessionStorage.removeItem(SESSION_KEY);
          onSignOut();
        }}>
          Sign out
        </Button>
      </aside>

      <section className="min-w-0 space-y-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
              02 — Research
            </p>
            <h1 className="font-display text-4xl font-extrabold leading-[0.95] md:text-5xl">
              Review with a clearer view.
            </h1>
            <p className="mt-2 text-muted-foreground">Evidence for your next human decision.</p>
          </div>
          <Badge variant="outline">Synthetic demo</Badge>
        </div>

        <div className="flex flex-wrap gap-2">
          {(
            [
              ["research", "Credit research"],
              ["profiles", "Prospect profiles"],
              ["log", "Decision log"],
            ] as const
          ).map(([id, label]) => (
            <Button
              key={id}
              variant={tab === id ? "default" : "outline"}
              onClick={() => setTab(id)}
            >
              {label}
            </Button>
          ))}
        </div>

        {tab === "research" && (
          <>
            <div className="rounded-2xl border border-border p-4">
              <div className="mb-2 flex items-center gap-2">
                <span className="grid size-8 place-items-center rounded-full bg-primary font-display font-bold text-primary-foreground">
                  B
                </span>
                <p className="font-display font-bold">Ask Bessie</p>
                <Badge variant="secondary">Mock</Badge>
              </div>
              <div className="flex gap-2">
                <Input
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Why does this prospect need review?"
                  aria-label="Ask Bessie"
                  onKeyDown={(event) => {
                    if (event.key === "Enter") ask();
                  }}
                />
                <Button size="icon" aria-label="Ask" onClick={ask}>
                  <ArrowRight aria-hidden="true" />
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Grounded in the policy evidence below.
              </p>
              {answer && <p className="mt-3 text-sm">{answer}</p>}
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
              <p>
                <Lock className="mr-1 inline size-3.5" aria-hidden="true" />
                Application review · {prospect.id}
              </p>
              <p>Access expires in 12 min</p>
            </div>

            <div>
              <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">
                {prospect.id} / {prospect.product}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-3">
                <h2 className="font-display text-3xl font-extrabold">{prospect.headline}</h2>
                {prospect.refer && <Badge>Refer</Badge>}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {prospect.summary} pnc-demo-v1 · Data as of {prospect.asOf}
              </p>
            </div>

            <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px]">
              <div className="overflow-x-auto rounded-2xl border border-border">
                <table className="w-full min-w-[520px] text-left text-sm">
                  <caption className="px-4 py-3 text-left font-display text-base font-bold">
                    Rule-by-rule evidence
                  </caption>
                  <thead className="text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="px-4 py-2 font-medium">Rule</th>
                      <th className="px-4 py-2 font-medium">Value</th>
                      <th className="px-4 py-2 font-medium">Policy target</th>
                      <th className="px-4 py-2 font-medium">Result</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prospect.rules.map((rule) => (
                      <tr key={rule.rule} className="border-t border-border">
                        <td className="px-4 py-2">{rule.rule}</td>
                        <td className="px-4 py-2">{rule.value}</td>
                        <td className="px-4 py-2 text-muted-foreground">{rule.target}</td>
                        <td className="px-4 py-2">
                          {rule.result === "Pass" ? (
                            <span className="inline-flex items-center gap-1 text-primary">
                              <Check className="size-3.5" aria-hidden="true" /> Pass
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1">
                              <TriangleAlert className="size-3.5" aria-hidden="true" /> Watch
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="space-y-3">
                <article className="rounded-2xl border border-border p-4">
                  <h3 className="font-display font-bold">Strengths & concerns</h3>
                  <p className="mt-2 text-sm text-muted-foreground">{prospect.strengths}</p>
                </article>
                <article className="rounded-2xl border border-border p-4">
                  <h3 className="font-display font-bold">Missing inputs</h3>
                  <p className="mt-2 text-sm text-muted-foreground">{prospect.missing}</p>
                </article>
                <article className="rounded-2xl border border-border p-4">
                  <h3 className="font-display font-bold">What would change the outcome?</h3>
                  <p className="mt-2 text-sm text-primary">{prospect.change.amount}</p>
                  <p className="mt-1 text-sm text-muted-foreground">{prospect.change.detail}</p>
                  <p className="mt-2 text-sm">
                    Recomputed scenario: {prospect.change.scenario}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {prospect.change.apr} · Synthetic, not an offer.
                  </p>
                </article>
              </div>
            </div>

            <div className="rounded-2xl border border-border p-4">
              <h3 className="font-display font-bold">Your decision</h3>
              <p className="mb-3 text-sm text-muted-foreground">
                Choose an action and enter your rationale. Nothing is sent externally.
              </p>
              <div className="flex flex-col gap-2 md:flex-row">
                <Select value={decision} onValueChange={setDecision}>
                  <SelectTrigger className="md:w-56" aria-label="Select a decision">
                    <SelectValue placeholder="Select a decision" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Approve">Approve</SelectItem>
                    <SelectItem value="Refer">Refer</SelectItem>
                    <SelectItem value="Decline">Decline</SelectItem>
                  </SelectContent>
                </Select>
                <Input
                  value={rationale}
                  onChange={(event) => setRationale(event.target.value)}
                  placeholder="Add your rationale..."
                  aria-label="Rationale"
                />
                <Button
                  disabled={!decision || !rationale.trim()}
                  onClick={() => {
                    setLog((rows) => [
                      {
                        id: `${prospect.id}-${rows.length + 1}`,
                        prospectId: prospect.id,
                        decision,
                        rationale: rationale.trim(),
                      },
                      ...rows,
                    ]);
                    setRationale("");
                    setTab("log");
                  }}
                >
                  Record simulated decision
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                Overrides require a written reason and are flagged for compliance review.
              </p>
            </div>
          </>
        )}

        {tab === "profiles" && (
          <div className="grid gap-3 sm:grid-cols-2">
            {PROSPECTS.map((item) => (
              <article key={item.id} className="rounded-2xl border border-border p-4">
                <p className="font-display font-bold">{item.id}</p>
                <p className="text-sm text-muted-foreground">{item.product}</p>
                <p className="mt-2 text-sm">{blind ? "Identity hidden for blind review." : item.headline}</p>
                <p className="mt-2 text-sm text-muted-foreground">{item.summary}</p>
              </article>
            ))}
          </div>
        )}

        {tab === "log" && (
          <div className="space-y-3">
            {log.length === 0 && (
              <p className="text-sm text-muted-foreground">No simulated decisions yet.</p>
            )}
            {log.map((entry) => (
              <article key={entry.id} className="rounded-2xl border border-border p-4">
                <p className="font-display font-bold">
                  {entry.prospectId} · {entry.decision}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{entry.rationale}</p>
              </article>
            ))}
          </div>
        )}
        <p className="text-xs text-muted-foreground">
          Synthetic data. Prototype policy rules, not bank policy.
        </p>
      </section>
    </div>
  );
}
