import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { staffFetch } from "@/lib/staff-api";

type Bucket = "stocks" | "bonds" | "foreign";
type Allocation = Record<Bucket, number>;
type Client = { client_id: number; name: string; synthetic: boolean };
type Metrics = {
  annualized_return: number;
  total_return: number;
  volatility: number;
  max_drawdown: number;
};
type Assessment = {
  metrics: Metrics;
  benchmark: Metrics;
  risk_capacity: string;
  stated_tolerance: number;
  risk_budget: number;
  risk_limits?: Record<string, number | null>;
  binding_limits?: string[];
  profile_model?: {
    allocations: Allocation;
    metrics: Metrics;
    goal_feasible: boolean;
    same_as_current?: boolean;
    requires_approval: boolean;
  } | null;
  flags: string[];
  missing_inputs: string[];
  allocations: Allocation;
  data_as_of: string;
  window_start: string;
  history_stale: boolean;
  method: string;
  limitations: string[];
  financial_context: {
    monthly_income: number;
    monthly_debt_payment: number;
    recurring_bills: number;
    emergency_fund_months: number;
    income_volatility: number;
    monthly_surplus: number;
    finance_as_of: string;
  };
  return_history: {
    date: string;
    portfolio_index: number;
    benchmark_index: number;
  }[];
};
type Profile = {
  goal: string;
  horizon_months: number;
  tolerance: number;
  liquidity_need_cents: number;
  target_return: number;
  synthetic: boolean;
  questionnaire: { source?: string };
};
type Proposal = {
  id: string;
  status: string;
  base_revision: number;
  before: Assessment;
  after: Assessment;
  rationale: string;
  estimated_cost_cents: number;
  cost_assumption: string;
  goal_feasible: boolean;
  no_change?: boolean;
  approval_allowed?: boolean;
  constraint_violations?: {
    code: string;
    message: string;
    actual: number;
    limit: number;
  }[];
  trades: { bucket: Bucket; delta_cents: number }[];
};
type Detail = {
  client_id: number;
  name: string;
  revision: number;
  value_cents: number;
  as_of: string;
  allocations: Allocation;
  profile: Profile;
  holdings: {
    bucket: Bucket;
    instrument: string;
    asset_class: string;
    geography: string;
    currency: string;
    value_cents: number;
    units: number;
  }[];
  assessment: Assessment | null;
  assessment_history?: {
    id: string;
    assessed_at: string;
    revision: number;
    metrics: Metrics;
    risk_capacity: string;
    risk_budget: number;
  }[];
  proposals: Proposal[];
  disclaimer: string;
  history: {
    id: string;
    recorded_at: string;
    event: string;
    rationale?: string;
    value_cents?: number;
    allocations?: Allocation;
  }[];
  financial_history: {
    date: string;
    portfolio_value: number | null;
    monthly_savings_contribution: number | null;
    income_volatility: number | null;
    late_payments: number | null;
  }[];
  behavior: { note: string; snapshot_count: number };
};
const BUCKETS: Bucket[] = ["stocks", "bonds", "foreign"];
const LABEL: Record<Bucket, string> = {
  stocks: "Domestic stocks",
  bonds: "Domestic bonds",
  foreign: "Foreign-market equities",
};
const SECTIONS = [
  "Overview",
  "Risk & returns",
  "Profile",
  "Rebalance",
  "History",
] as const;
const money = (cents: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    cents / 100,
  );
const pct = (value: number) => `${(value * 100).toFixed(2)}%`;
const title = (value: string) => value.replaceAll("_", " ");
function Card({
  title: heading,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-border bg-background p-5 space-y-3">
      <h2 className="font-display text-lg font-bold">{heading}</h2>
      {children}
    </section>
  );
}
function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-muted/40 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 font-display text-xl font-bold">{value}</p>
    </div>
  );
}
function AllocationView({ values }: { values: Allocation }) {
  return (
    <div className="space-y-3">
      {BUCKETS.map((bucket, i) => (
        <div key={bucket}>
          <div className="mb-1 flex justify-between gap-2 text-sm">
            <span>{LABEL[bucket]}</span>
            <strong>{pct(values[bucket])}</strong>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-muted">
            <div
              className={
                i === 1
                  ? "h-full bg-blue-400"
                  : i === 2
                    ? "h-full bg-violet-400"
                    : "h-full bg-primary"
              }
              style={{ width: pct(values[bucket]) }}
            />
          </div>
        </div>
      ))}
      <p className="text-xs text-muted-foreground">
        Total: {pct(BUCKETS.reduce((sum, k) => sum + values[k], 0))}. Foreign
        equities are counted in the foreign bucket once.
      </p>
    </div>
  );
}

export function PortfolioWorkspace({
  focused,
  onContext,
}: {
  focused: boolean;
  onContext: (context: {
    featureId: string;
    resourceId?: string | undefined;
    hint: string;
  }) => void;
}) {
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Overview");
  const [assignOpen, setAssignOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const queue = useQuery({
    queryKey: ["staff", "portfolio-clients"],
    queryFn: () => staffFetch<{ clients: Client[] }>("/portfolio/clients"),
  });
  const directory = useQuery({
    queryKey: ["staff", "portfolio-unassigned", search],
    enabled: assignOpen,
    queryFn: () =>
      staffFetch<{ clients: Client[] }>(
        `/portfolio/unassigned?search=${encodeURIComponent(search)}`,
      ),
  });
  const detail = useQuery({
    queryKey: ["staff", "portfolio-client", selected],
    enabled: selected !== null,
    queryFn: () => staffFetch<Detail>(`/portfolio/clients/${selected}`),
  });
  useEffect(() => {
    if (focused)
      onContext({
        featureId: "staff.portfolio",
        resourceId: selected === null ? undefined : String(selected),
        hint:
          selected === null
            ? "Select an assigned client to discuss their portfolio."
            : "Bessie explains this client's authorized portfolio assessment.",
      });
  }, [focused, selected, onContext]);
  const act = async <T,>(
    work: () => Promise<T>,
    message: string,
  ): Promise<T | undefined> => {
    if (busy) return undefined;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await work();
      await Promise.all(
        [
          "portfolio-client",
          "portfolio-clients",
          "portfolio-unassigned",
          "portfolio-summary",
          "portfolio-activity",
        ].map((key) =>
          queryClient.invalidateQueries({ queryKey: ["staff", key] }),
        ),
      );
      setNotice(message);
      return result;
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "The portfolio request failed.",
      );
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  const choose = (id: number) => {
    setSelected(id);
    setSection("Overview");
    setError(null);
    setNotice(null);
  };
  const data = detail.data;
  const assessment = data?.assessment;
  return (
    <div className="w-full space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs uppercase tracking-widest text-primary">
            Portfolio / Risk Manager
          </p>
          <h1 className="font-display text-4xl font-extrabold">
            Your client portfolios
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Review exposure, understand financial capacity, and approve a
            modeled rebalance.
          </p>
        </div>
        <Button onClick={() => setAssignOpen(!assignOpen)}>
          {assignOpen ? "Close assignment" : "Assign client"}
        </Button>
      </div>
      <p className="rounded-xl border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        Synthetic portfolios and market history. Performance is modeled, not
        actual account returns. Rebalances are simulated; no brokerage orders
        are sent.
      </p>
      <AssignedPortfolioSummary />
      {error && section !== "Profile" && section !== "Rebalance" && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      {notice && section !== "Profile" && (
        <p role="status" className="text-sm text-primary">
          {notice}
        </p>
      )}
      {assignOpen && (
        <Card title="Assign an unassigned client to yourself">
          <Input
            aria-label="Search unassigned clients"
            placeholder="Search client name"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            Only names and client IDs are available until assignment. Existing
            manager assignments are protected.
          </p>
          {directory.isLoading && <p>Loading clients…</p>}
          {directory.error && <p role="alert">{directory.error.message}</p>}
          <div className="max-h-60 overflow-y-auto space-y-2">
            {directory.data?.clients.map((c) => (
              <div
                key={c.client_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-border p-3"
              >
                <span className="text-sm">
                  {c.name} · {c.client_id}
                </span>
                <Button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await staffFetch("/portfolio/assignments", {
                        body: { client_id: c.client_id },
                      });
                      choose(c.client_id);
                      setAssignOpen(false);
                    }, "Client assigned to your workspace.")
                  }
                >
                  Assign to me
                </Button>
              </div>
            ))}
            {directory.data?.clients.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No unassigned clients match. Assigned clients are not available
                for self-reassignment.
              </p>
            )}
          </div>
        </Card>
      )}
      <div className="grid gap-5 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="space-y-3">
          <h2 className="font-display font-bold">Assigned clients</h2>
          <Input
            aria-label="Filter assigned clients"
            placeholder="Filter your queue"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
          {queue.isLoading && <p>Loading queue…</p>}
          {queue.error && <p role="alert">{queue.error.message}</p>}
          <div className="space-y-2">
            {queue.data?.clients
              .filter((c) =>
                `${c.name} ${c.client_id}`
                  .toLowerCase()
                  .includes(filter.toLowerCase()),
              )
              .map((c) => (
                <button
                  key={c.client_id}
                  type="button"
                  aria-pressed={selected === c.client_id}
                  onClick={() => choose(c.client_id)}
                  className={`w-full rounded-xl border p-3 text-left text-sm ${selected === c.client_id ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"}`}
                >
                  <span className="block font-bold">{c.name}</span>
                  <span className="text-xs text-muted-foreground">
                    Client {c.client_id} · synthetic
                  </span>
                </button>
              ))}
          </div>
          {queue.data?.clients.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Your queue is empty. Use Assign client to get started.
            </p>
          )}
        </aside>
        <div className="min-w-0 space-y-4">
          {selected === null ? (
            <Card title="Choose a client">
              <p className="text-sm text-muted-foreground">
                Assign a client or select one from your queue. Their private
                financial context stays unavailable to other managers.
              </p>
            </Card>
          ) : (
            <>
              {detail.isLoading && <p role="status">Loading portfolio…</p>}
              {detail.error && <p role="alert">{detail.error.message}</p>}
              {data && (
                <>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h2 className="font-display text-2xl font-extrabold">
                        {data.name}
                      </h2>
                      <p className="text-xs text-muted-foreground">
                        Client {data.client_id} · Revision {data.revision} ·
                        Portfolio as of {data.as_of}
                      </p>
                    </div>
                    <Button
                      disabled={busy}
                      onClick={() =>
                        void act(
                          () =>
                            staffFetch(
                              `/portfolio/clients/${selected}/assessments`,
                              { body: {} },
                            ),
                          "Risk assessment saved.",
                        )
                      }
                    >
                      Run risk assessment
                    </Button>
                  </div>
                  <nav
                    aria-label="Portfolio sections"
                    className="flex flex-wrap gap-2"
                  >
                    {SECTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setSection(s)}
                        aria-current={section === s ? "page" : undefined}
                        className={`rounded-full border px-3 py-2 text-xs ${section === s ? "border-primary text-primary" : "border-border"}`}
                      >
                        {s}
                      </button>
                    ))}
                  </nav>
                  {section === "Overview" && (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <Metric
                          label="Modeled portfolio value"
                          value={money(data.value_cents)}
                        />
                        <Metric
                          label="Stated tolerance"
                          value={`${data.profile.tolerance} / 5`}
                        />
                        <Metric
                          label="Financial risk capacity"
                          value={assessment?.risk_capacity ?? "Run assessment"}
                        />
                        <Metric
                          label="Portfolio volatility"
                          value={
                            assessment
                              ? pct(assessment.metrics.volatility)
                              : "Not assessed"
                          }
                        />
                      </div>
                      <Card title="Current asset allocation">
                        <AllocationView values={data.allocations} />
                      </Card>
                      <Card title="Holdings">
                        <div className="overflow-x-auto">
                          <table className="w-full text-left text-xs">
                            <thead>
                              <tr>
                                <th className="p-2">Instrument</th>
                                <th className="p-2">Class / geography</th>
                                <th className="p-2">Value</th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.holdings.map((h) => (
                                <tr
                                  key={h.bucket}
                                  className="border-t border-border"
                                >
                                  <td className="p-2">{h.instrument}</td>
                                  <td className="p-2">
                                    {h.asset_class} / {h.geography}
                                  </td>
                                  <td className="p-2">
                                    {money(h.value_cents)}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </Card>
                      {assessment && (
                        <Card title="Review flags">
                          {assessment.flags.length ? (
                            <ul className="list-inside list-disc text-sm">
                              {assessment.flags.map((f) => (
                                <li key={f}>{title(f)}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm">
                              No risk-budget or concentration flags in this
                              assessment.
                            </p>
                          )}
                        </Card>
                      )}
                    </>
                  )}
                  {section === "Risk & returns" &&
                    (assessment ? (
                      <>
                        <div className="grid grid-cols-2 gap-3">
                          <Metric
                            label="Annualized modeled return"
                            value={pct(assessment.metrics.annualized_return)}
                          />
                          <Metric
                            label="Annualized volatility"
                            value={pct(assessment.metrics.volatility)}
                          />
                          <Metric
                            label="Maximum drawdown"
                            value={pct(assessment.metrics.max_drawdown)}
                          />
                          <Metric
                            label="Risk budget"
                            value={pct(assessment.risk_budget)}
                          />
                          <Metric
                            label="Annual return goal"
                            value={pct(data.profile.target_return)}
                          />
                          <Metric
                            label="Investment horizon"
                            value={`${data.profile.horizon_months} months`}
                          />
                        </div>
                        <Card title="Profile alignment">
                          {assessment.binding_limits && (
                            <div className="rounded-xl bg-muted/40 p-3 text-sm">
                              <p className="font-bold">
                                Binding limit:{" "}
                                {assessment.binding_limits
                                  .map(title)
                                  .join(" and ")}{" "}
                                ({pct(assessment.risk_budget)})
                              </p>
                              <ul className="mt-2 space-y-1 text-xs">
                                {Object.entries(
                                  assessment.risk_limits ?? {},
                                ).map(([name, limit]) => (
                                  <li key={name}>
                                    {title(name)}:{" "}
                                    {limit === null
                                      ? "No additional cap"
                                      : pct(limit)}
                                  </li>
                                ))}
                              </ul>
                              <p className="mt-2 text-xs text-muted-foreground">
                                Prototype horizon limits: under 36 months, 6%;
                                36–83 months, 12%; 84+ months, 20%. Increasing
                                tolerance cannot override a shorter horizon or
                                lower financial capacity.
                              </p>
                            </div>
                          )}
                          <p className="text-sm">
                            Stated tolerance: {data.profile.tolerance} / 5.
                            Financial capacity: {assessment.risk_capacity}.
                          </p>
                          {assessment.flags.length ? (
                            <ul className="list-inside list-disc text-sm">
                              {assessment.flags.map((flag) => (
                                <li key={flag}>{title(flag)}</li>
                              ))}
                            </ul>
                          ) : (
                            <p className="text-sm">
                              The current assessment has no review flags.
                            </p>
                          )}
                          <p className="text-xs text-muted-foreground">
                            Saving the profile refreshes risk limits and goal
                            comparisons. Historical returns and volatility
                            reflect the holdings and market history; changing
                            preferences alone does not change them.
                          </p>
                        </Card>
                        {assessment.profile_model && (
                          <Card title="Suggested allocation based on your profile">
                            <p className="text-sm text-muted-foreground">
                              Compare your saved holdings with the mix suggested
                              for your profile and risk limits. Approving a
                              custom rebalance updates your current holdings;
                              the suggestion may stay the same while your
                              profile and risk limits remain unchanged. A
                              suggestion is only applied through an approved
                              rebalance.
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Historical replay using synthetic market data, not
                              a future-return forecast.
                            </p>
                            {assessment.profile_model.same_as_current && (
                              <p className="text-sm">
                                Your current allocation already matches this
                                suggested mix, so the curves overlap.
                              </p>
                            )}
                            <div className="grid gap-5 md:grid-cols-2">
                              <div className="space-y-3">
                                <h3 className="font-display font-bold">
                                  Current portfolio
                                </h3>
                                <AllocationView values={data.allocations} />
                                <div className="grid grid-cols-2 gap-3">
                                  <Metric
                                    label="Current volatility"
                                    value={pct(assessment.metrics.volatility)}
                                  />
                                  <Metric
                                    label="Current annualized return"
                                    value={pct(
                                      assessment.metrics.annualized_return,
                                    )}
                                  />
                                </div>
                              </div>
                              <div className="space-y-3">
                                <h3 className="font-display font-bold">
                                  Suggested allocation
                                </h3>
                                <AllocationView
                                  values={assessment.profile_model.allocations}
                                />
                                <div className="grid grid-cols-2 gap-3">
                                  <Metric
                                    label="Suggested volatility"
                                    value={pct(
                                      assessment.profile_model.metrics
                                        .volatility,
                                    )}
                                  />
                                  <Metric
                                    label="Suggested annualized return"
                                    value={pct(
                                      assessment.profile_model.metrics
                                        .annualized_return,
                                    )}
                                  />
                                </div>
                              </div>
                            </div>
                            {!assessment.profile_model.goal_feasible && (
                              <p className="text-sm text-amber-500">
                                The return goal is not met by this historical
                                model within the risk budget.
                              </p>
                            )}
                          </Card>
                        )}
                        <Card title="Historical model vs benchmark">
                          <p className="text-xs text-muted-foreground">
                            {assessment.window_start} to {assessment.data_as_of}{" "}
                            · Initial index 100 · gross of costs
                          </p>
                          <p className="text-xs text-muted-foreground">
                            All portfolios start at 100. An index of 120 means a
                            20% cumulative gain; 90 means a 10% loss. These
                            values are not allocation percentages.
                          </p>
                          <div className="h-64 w-full">
                            <ResponsiveContainer width="100%" height="100%">
                              <LineChart data={assessment.return_history}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis
                                  dataKey="date"
                                  tick={{ fontSize: 10 }}
                                  minTickGap={60}
                                />
                                <YAxis
                                  width={80}
                                  tick={{ fontSize: 10 }}
                                  label={{
                                    value:
                                      "Portfolio value index (start = 100)",
                                    angle: -90,
                                    position: "insideLeft",
                                    style: {
                                      fontSize: 10,
                                      textAnchor: "middle",
                                      fill: "#a3a3a3",
                                    },
                                  }}
                                />
                                <Tooltip
                                  formatter={(value) =>
                                    `${Number(value).toFixed(2)} index points`
                                  }
                                />
                                <Legend />
                                <Line
                                  name="Current portfolio performance"
                                  type="monotone"
                                  dataKey="portfolio_index"
                                  stroke="#a3e635"
                                  dot={false}
                                />
                                <Line
                                  name="Benchmark"
                                  type="monotone"
                                  dataKey="benchmark_index"
                                  stroke="#60a5fa"
                                  dot={false}
                                />
                                {assessment.profile_model && (
                                  <Line
                                    name="Suggested portfolio performance"
                                    type="monotone"
                                    dataKey="profile_model_index"
                                    stroke="#c084fc"
                                    strokeDasharray="5 3"
                                    dot={false}
                                  />
                                )}
                              </LineChart>
                            </ResponsiveContainer>
                          </div>
                          <p className="text-xs text-muted-foreground">
                            {assessment.method}
                          </p>
                          <p className="text-xs">
                            Benchmark annualized return:{" "}
                            {pct(assessment.benchmark.annualized_return)}
                          </p>
                          {assessment.history_stale && (
                            <p className="text-sm text-amber-500">
                              Historical market window is over 90 days old.
                            </p>
                          )}
                        </Card>
                        <Card title="Capacity and financial context">
                          <div className="grid grid-cols-2 gap-3">
                            <Metric
                              label="Monthly income"
                              value={money(
                                assessment.financial_context.monthly_income *
                                  100,
                              )}
                            />
                            <Metric
                              label="Monthly surplus after bills and debt"
                              value={money(
                                assessment.financial_context.monthly_surplus *
                                  100,
                              )}
                            />
                            <Metric
                              label="Emergency fund"
                              value={`${assessment.financial_context.emergency_fund_months.toFixed(1)} months`}
                            />
                            <Metric
                              label="Income volatility"
                              value={pct(
                                assessment.financial_context.income_volatility,
                              )}
                            />
                          </div>
                          <p className="text-xs text-muted-foreground">
                            Financial snapshot:{" "}
                            {assessment.financial_context.finance_as_of}. Risk
                            capacity, willingness to take risk, and current
                            exposure are assessed separately.
                          </p>
                        </Card>
                        <Card title="Assumptions and limitations">
                          <ul className="list-inside list-disc text-xs text-muted-foreground">
                            {assessment.limitations.map((v) => (
                              <li key={v}>{v}</li>
                            ))}
                          </ul>
                        </Card>
                      </>
                    ) : (
                      <Card title="Assessment needed">
                        <p>
                          Run a risk assessment to view risk and historical
                          modeled returns.
                        </p>
                      </Card>
                    ))}
                  {section === "Profile" && (
                    <ProfileEditor
                      key={`${selected}:${data.revision}`}
                      profile={data.profile}
                      busy={busy}
                      confirmation={notice}
                      saveError={error}
                      onEdit={() => {
                        setNotice(null);
                        setError(null);
                      }}
                      save={(body) =>
                        void act(
                          () =>
                            staffFetch(
                              `/portfolio/clients/${selected}/profile`,
                              { method: "PUT", body },
                            ),
                          "Profile saved. Risk assessment and goal comparisons updated.",
                        )
                      }
                    />
                  )}
                  {section === "Rebalance" && (
                    <RebalanceEditor
                      key={`${selected}:${data.revision}`}
                      detail={data}
                      busy={busy}
                      requestError={error}
                      onEdit={() => {
                        setNotice(null);
                        setError(null);
                      }}
                      propose={(body) =>
                        act(
                          () =>
                            staffFetch<Proposal>(
                              `/portfolio/clients/${selected}/proposals`,
                              { body },
                            ),
                          "Allocation preview ready.",
                        )
                      }
                      approve={(id, rationale) =>
                        void act(
                          () =>
                            staffFetch(
                              `/portfolio/clients/${selected}/proposals/${id}/approve`,
                              { body: { rationale, confirm_simulated: true } },
                            ),
                          "Simulated rebalance approved. No orders were sent.",
                        )
                      }
                    />
                  )}
                  {section === "History" && (
                    <>
                      <Card title="Observed financial patterns">
                        <p className="text-sm text-muted-foreground">
                          {data.behavior.note}
                        </p>
                        <div className="max-h-72 overflow-auto">
                          <table className="w-full text-xs text-left">
                            <thead>
                              <tr>
                                <th className="p-2">Date</th>
                                <th className="p-2">Tracker portfolio value</th>
                                <th className="p-2">
                                  Monthly savings contribution
                                </th>
                                <th className="p-2">
                                  Late payments, trailing year
                                </th>
                              </tr>
                            </thead>
                            <tbody>
                              {data.financial_history.map((f) => (
                                <tr
                                  className="border-t border-border"
                                  key={f.date}
                                >
                                  <td className="p-2">{f.date}</td>
                                  <td className="p-2">
                                    {f.portfolio_value === null
                                      ? "Unavailable"
                                      : money(f.portfolio_value * 100)}
                                  </td>
                                  <td className="p-2">
                                    {f.monthly_savings_contribution === null
                                      ? "Unavailable"
                                      : money(
                                          f.monthly_savings_contribution * 100,
                                        )}
                                  </td>
                                  <td className="p-2">
                                    {f.late_payments ?? "Unavailable"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </Card>
                      <Card title="Risk assessment history">
                        {(data.assessment_history ?? []).length === 0 && (
                          <p className="text-sm text-muted-foreground">
                            No saved assessments yet.
                          </p>
                        )}
                        {(data.assessment_history ?? []).map((a) => (
                          <article
                            key={a.id}
                            className="border-b border-border pb-3 text-sm"
                          >
                            <p className="font-bold">
                              Revision {a.revision} · {a.risk_capacity} capacity
                            </p>
                            <p className="text-xs text-muted-foreground">
                              {a.assessed_at}
                            </p>
                            <p className="text-xs">
                              Volatility {pct(a.metrics.volatility)} · budget{" "}
                              {pct(a.risk_budget)} · modeled annual return{" "}
                              {pct(a.metrics.annualized_return)}
                            </p>
                          </article>
                        ))}
                      </Card>
                      <Card title="Portfolio change history">
                        {data.history.map((h) => (
                          <article
                            key={h.id}
                            className="border-b border-border pb-3 text-sm"
                          >
                            <p className="font-bold">{title(h.event)}</p>
                            <p className="text-xs text-muted-foreground">
                              {h.recorded_at}
                            </p>
                            {h.rationale && <p>{h.rationale}</p>}
                            {h.allocations && (
                              <p className="text-xs">
                                {BUCKETS.map(
                                  (k) =>
                                    `${LABEL[k]} ${pct(h.allocations![k])}`,
                                ).join(" · ")}
                              </p>
                            )}
                          </article>
                        ))}
                      </Card>
                    </>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function AssignedPortfolioSummary() {
  const [open, setOpen] = useState(false);
  const summary = useQuery({
    queryKey: ["staff", "portfolio-summary"],
    enabled: open,
    queryFn: () =>
      staffFetch<{
        assigned_clients: number;
        assessed_clients: number;
        needs_assessment: number;
        above_risk_budget: number;
        within_risk_budget: number;
        clients_with_pending_previews: number;
        mean_volatility: number | null;
        mean_annualized_return: number | null;
        aggregate_contributors: number;
        suppression_threshold: number;
        aggregate_note: string;
        method: string;
      }>("/portfolio/summary"),
  });
  const data = summary.data;
  return (
    <details
      className="rounded-2xl border border-border p-4"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer font-display font-bold">
        Assigned portfolio overview
      </summary>
      <p className="mt-2 text-xs text-muted-foreground">
        Only clients assigned to you. Counts and averages refresh after
        assignments, profile updates, assessments and approved rebalances.
      </p>
      {summary.isLoading && (
        <p role="status">Loading assigned portfolio overview…</p>
      )}
      {summary.error && <p role="alert">{summary.error.message}</p>}
      {data && (
        <div className="mt-3 space-y-3">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Metric
              label="Assigned clients"
              value={String(data.assigned_clients)}
            />
            <Metric
              label="Current assessments"
              value={String(data.assessed_clients)}
            />
            <Metric
              label="Need an assessment"
              value={String(data.needs_assessment)}
            />
            <Metric
              label="Above risk budget"
              value={String(data.above_risk_budget)}
            />
            <Metric
              label="Within risk budget"
              value={String(data.within_risk_budget)}
            />
            <Metric
              label="Clients with pending previews"
              value={String(data.clients_with_pending_previews)}
            />
            <Metric
              label="Mean portfolio volatility"
              value={
                data.mean_volatility === null
                  ? "Awaiting assessments"
                  : pct(data.mean_volatility)
              }
            />
            <Metric
              label="Mean modeled annual return"
              value={
                data.mean_annualized_return === null
                  ? "Awaiting assessments"
                  : pct(data.mean_annualized_return)
              }
            />
          </div>
          {data.aggregate_contributors < data.suppression_threshold && (
            <p className="text-sm text-amber-500">
              {data.aggregate_contributors} of {data.suppression_threshold}{" "}
              required current assessments available. Run assessments for the
              remaining assigned clients to show risk and return averages.
            </p>
          )}
          <p className="text-xs text-muted-foreground">{data.aggregate_note}</p>
          <p className="text-xs text-muted-foreground">{data.method}</p>
        </div>
      )}
    </details>
  );
}

function ProfileEditor({
  profile,
  busy,
  confirmation,
  saveError,
  onEdit,
  save,
}: {
  profile: Profile;
  busy: boolean;
  confirmation: string | null;
  saveError: string | null;
  onEdit: () => void;
  save: (body: unknown) => void;
}) {
  const [goal, setGoal] = useState(profile.goal);
  const [horizon, setHorizon] = useState(String(profile.horizon_months));
  const [tolerance, setTolerance] = useState(String(profile.tolerance));
  const [liquidity, setLiquidity] = useState(
    String(profile.liquidity_need_cents / 100),
  );
  const [target, setTarget] = useState(String(profile.target_return * 100));
  return (
    <Card title="Investment profile">
      <p className="text-xs text-muted-foreground">
        {profile.questionnaire.source}. These are prototype assumptions, not
        confirmed client questionnaire responses.
      </p>
      <form
        className="space-y-3"
        onChange={onEdit}
        onSubmit={(e) => {
          e.preventDefault();
          save({
            goal,
            horizon_months: Number(horizon),
            tolerance: Number(tolerance),
            liquidity_need_cents: Math.round(Number(liquidity) * 100),
            target_return: (Number(target) / 100).toFixed(6),
          });
        }}
      >
        <label className="block text-sm">
          Goal
          <Input
            required
            minLength={3}
            maxLength={200}
            value={goal}
            onChange={(e) => setGoal(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Investment horizon (months)
          <Input
            type="number"
            min={1}
            max={600}
            required
            value={horizon}
            onChange={(e) => setHorizon(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Stated risk tolerance (1 cautious to 5 aggressive)
          <Input
            type="number"
            min={1}
            max={5}
            required
            value={tolerance}
            onChange={(e) => setTolerance(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Liquidity needed (USD)
          <Input
            type="number"
            min={0}
            step="0.01"
            required
            value={liquidity}
            onChange={(e) => setLiquidity(e.target.value)}
          />
        </label>
        <label className="block text-sm">
          Annual return goal (%)
          <Input
            type="number"
            min={0}
            max={30}
            step="0.01"
            required
            value={target}
            onChange={(e) => setTarget(e.target.value)}
          />
        </label>
        <Button disabled={busy} type="submit">
          {busy ? "Saving profile…" : "Save investment profile"}
        </Button>
        {confirmation && (
          <p
            role="status"
            className="rounded-xl border border-primary/30 bg-primary/10 p-3 text-sm text-primary"
          >
            {confirmation}
          </p>
        )}
        {saveError && (
          <p role="alert" className="text-sm text-destructive">
            {saveError}
          </p>
        )}
      </form>
    </Card>
  );
}

function RebalanceEditor({
  detail,
  busy,
  requestError,
  onEdit,
  propose,
  approve,
}: {
  detail: Detail;
  busy: boolean;
  requestError: string | null;
  onEdit: () => void;
  propose: (body: unknown) => Promise<Proposal | undefined>;
  approve: (id: string, rationale: string) => void;
}) {
  const existingProposal = detail.proposals.find(
    (v) => v.status === "proposed" && v.base_revision === detail.revision,
  );
  const initialWeights =
    existingProposal?.after.allocations ?? detail.allocations;
  const [weights, setWeights] = useState<Record<Bucket, string>>({
    stocks: String(initialWeights.stocks * 100),
    bonds: String(initialWeights.bonds * 100),
    foreign: String(initialWeights.foreign * 100),
  });
  const [rationale, setRationale] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [selectedProposal, setSelectedProposal] = useState<
    Proposal | undefined
  >(existingProposal);
  const total = BUCKETS.reduce((s, k) => s + Number(weights[k]), 0);
  const valid =
    Math.abs(total - 100) < 0.000001 &&
    BUCKETS.every((k) => Number(weights[k]) >= 0 && Number(weights[k]) <= 100);
  const p = dirty ? undefined : selectedProposal;
  const noChange =
    p &&
    (p.no_change ??
      BUCKETS.every(
        (k) =>
          Math.abs(p.before.allocations[k] - p.after.allocations[k]) <
          0.0000005,
      ));
  const approvalAllowed =
    p &&
    !noChange &&
    (p.approval_allowed ??
      (p.after.metrics.volatility <= p.after.risk_budget + 1e-8 &&
        Math.max(...BUCKETS.map((k) => p.after.allocations[k])) <= 0.8));
  const preview = async (custom: boolean) => {
    setDirty(true);
    onEdit();
    setConfirm(false);
    const result = await propose({
      rationale,
      ...(custom
        ? {
            allocations: Object.fromEntries(
              BUCKETS.map((k) => [k, (Number(weights[k]) / 100).toFixed(6)]),
            ),
          }
        : {}),
    });
    if (!result) return;
    setSelectedProposal(result);
    if (!custom)
      setWeights({
        stocks: String(result.after.allocations.stocks * 100),
        bonds: String(result.after.allocations.bonds * 100),
        foreign: String(result.after.allocations.foreign * 100),
      });
    setDirty(false);
  };
  return (
    <div className="space-y-4">
      <Card title="Build a rebalance proposal">
        <p className="text-sm text-muted-foreground">
          Automatic proposals search long-only mixes within the client's risk
          budget. A return goal can remain infeasible; the system will not raise
          risk just to meet it.
        </p>
        <label className="block text-sm">
          Review rationale
          <Textarea
            aria-label="Rebalance rationale"
            minLength={10}
            maxLength={2000}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
          />
        </label>
        <Button
          disabled={busy || rationale.trim().length < 10}
          onClick={() => void preview(false)}
        >
          Generate suitable allocation
        </Button>
        <h3 className="font-display font-bold">Custom allocation</h3>
        <p className="text-xs text-muted-foreground">
          Edit these percentages and click Preview my allocation. Generate
          suitable allocation calculates a mix from the profile instead of using
          these inputs.
        </p>
        <p className="text-xs text-muted-foreground">
          You can preview allocations above the limits to compare their risk and
          returns. Approval remains blocked until the allocation meets the
          client's limits.
        </p>
        <div className="grid gap-3 sm:grid-cols-3">
          {BUCKETS.map((k) => (
            <label key={k} className="text-xs">
              {LABEL[k]} (%)
              <Input
                disabled={busy}
                type="number"
                min={0}
                max={100}
                step="0.01"
                value={weights[k]}
                onChange={(e) => {
                  setWeights({ ...weights, [k]: e.target.value });
                  setDirty(true);
                  setConfirm(false);
                  onEdit();
                }}
              />
            </label>
          ))}
        </div>
        <p
          className={
            valid ? "text-xs text-muted-foreground" : "text-xs text-destructive"
          }
        >
          Allocation total: {total.toFixed(2)}% · must equal 100%
        </p>
        <Button
          variant="outline"
          disabled={busy || !valid || rationale.trim().length < 10}
          onClick={() => void preview(true)}
        >
          Preview my allocation
        </Button>
        {dirty && (
          <p role="status" className="text-sm text-amber-500">
            Your edited allocation has not been previewed. Review a successful
            preview before approving.
          </p>
        )}
        {requestError && (
          <p role="alert" className="text-sm text-destructive">
            {requestError}
          </p>
        )}
      </Card>
      {p && (
        <Card title="Review proposal before approval">
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <h3 className="mb-2 font-bold">Current</h3>
              <AllocationView values={p.before.allocations} />
              <p className="text-xs mt-2">
                Risk {pct(p.before.metrics.volatility)} · modeled return{" "}
                {pct(p.before.metrics.annualized_return)}
              </p>
            </div>
            <div>
              <h3 className="mb-2 font-bold">Proposed</h3>
              <AllocationView values={p.after.allocations} />
              <p className="text-xs mt-2">
                Risk {pct(p.after.metrics.volatility)} · modeled return{" "}
                {pct(p.after.metrics.annualized_return)}
              </p>
            </div>
          </div>
          <p className="text-sm">{p.rationale}</p>
          <ul className="text-xs space-y-1">
            {p.trades
              .filter((t) => t.delta_cents !== 0)
              .map((t) => (
                <li key={t.bucket}>
                  {t.delta_cents >= 0 ? "Buy" : "Sell"} {LABEL[t.bucket]}:{" "}
                  {money(Math.abs(t.delta_cents))}
                </li>
              ))}
          </ul>
          {noChange && (
            <p className="text-sm text-primary">
              No allocation change. No trades or rebalance approval are needed
              under the current settings.
            </p>
          )}
          <p className="text-xs">
            Estimated cost: {money(p.estimated_cost_cents)}. {p.cost_assumption}
            .
          </p>
          {!p.goal_feasible && (
            <p className="text-sm text-amber-500">
              Return goal is not met in this historical model. Review the goal
              or horizon; returns are not guaranteed.
            </p>
          )}
          {!noChange && (
            <>
              {!approvalAllowed && (
                <div
                  role="alert"
                  className="rounded-xl border border-amber-500/40 p-3 text-sm text-amber-500"
                >
                  <p className="font-bold">
                    Preview only — approval blocked by portfolio limits.
                  </p>
                  <ul className="mt-2 list-inside list-disc">
                    {p.constraint_violations?.map((v) => (
                      <li key={v.code}>
                        {v.message}: {pct(v.actual)} versus {pct(v.limit)}{" "}
                        allowed.
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2">
                    Your custom percentages are retained. Adjust them or
                    generate a suitable allocation.
                  </p>
                </div>
              )}
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  disabled={!approvalAllowed}
                  checked={confirm}
                  onChange={(e) => setConfirm(e.target.checked)}
                />
                I reviewed the proposal and understand this changes only the
                modeled portfolio. No real trades will be placed.
              </label>
              <Button
                disabled={
                  busy ||
                  !approvalAllowed ||
                  !confirm ||
                  rationale.trim().length < 10
                }
                onClick={() => approve(p.id, rationale)}
              >
                Approve simulated rebalance
              </Button>
            </>
          )}
        </Card>
      )}
      {detail.proposals.some(
        (v) => v.status === "proposed" && v.base_revision !== detail.revision,
      ) && (
        <p className="text-xs text-muted-foreground">
          Older proposals were based on a previous revision. Generate a fresh
          proposal before approval.
        </p>
      )}
    </div>
  );
}
