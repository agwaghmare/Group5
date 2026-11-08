import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { staffFetch } from "@/lib/staff-api";

type Event = {
  id: string;
  title: string;
  client_id: number;
  client_name: string;
  when: string;
  outcome: string;
  detail: string;
  fields: { label: string; value: string }[];
};
const FILTERS = [
  ["", "All activity"],
  ["portfolio_client_assigned", "Assignments"],
  ["portfolio_assessed", "Assessments"],
  ["portfolio_profile_updated", "Profile updates"],
  ["portfolio_rebalance_proposed", "Rebalance previews"],
  ["portfolio_rebalance_approved", "Approved rebalances"],
  ["portfolio_rebalance_blocked", "Blocked approvals"],
] as const;

export function PortfolioActivity() {
  const [filter, setFilter] = useState("");
  const activity = useQuery({
    queryKey: ["staff", "portfolio-activity", filter],
    queryFn: () =>
      staffFetch<{ events: Event[] }>(
        `/portfolio/activity${filter ? `?action=${encodeURIComponent(filter)}` : ""}`,
      ),
    refetchOnMount: "always",
  });
  return (
    <div className="max-w-4xl space-y-5">
      <p className="text-xs uppercase tracking-widest text-primary">
        Portfolio / Risk Manager
      </p>
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="font-display text-4xl font-extrabold">
          Your portfolio activity
        </h1>
        <Button
          disabled={activity.isFetching}
          onClick={() => void activity.refetch()}
        >
          Refresh activity
        </Button>
      </div>
      <p className="text-sm text-muted-foreground">
        Your client assignments, risk assessments, investment-profile changes
        and rebalance reviews. Previews and approved simulated changes are shown
        separately.
      </p>
      <label className="block text-sm">
        Activity type
        <select
          className="mt-2 block w-full rounded-xl border border-border bg-background p-3"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          {FILTERS.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {activity.isLoading && <p role="status">Loading portfolio activity…</p>}
      {activity.error && (
        <p role="alert" className="text-sm text-destructive">
          {activity.error.message}
        </p>
      )}
      {activity.data?.events.length === 0 && (
        <p className="rounded-2xl border border-border p-5 text-sm text-muted-foreground">
          No matching portfolio activity yet. Assign a client, run an
          assessment, update their profile or review a rebalance to add an
          entry.
        </p>
      )}
      <ul className="space-y-3">
        {activity.data?.events.map((e) => (
          <li
            key={e.id}
            className="rounded-2xl border border-border p-5 space-y-2"
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h2 className="font-display text-lg font-bold">{e.title}</h2>
              <span
                className={`rounded-full px-2 py-1 text-xs ${e.outcome === "denied" ? "bg-amber-500/10 text-amber-500" : "bg-muted text-muted-foreground"}`}
              >
                {e.outcome === "denied" ? "Blocked" : "Recorded"}
              </span>
            </div>
            <p className="text-sm">
              {e.client_name} · Client {e.client_id}
            </p>
            <p className="text-sm text-muted-foreground">{e.detail}</p>
            <details className="text-sm">
              <summary className="cursor-pointer text-xs text-primary">
                {new Date(e.when).toLocaleString()} · View details
              </summary>
              <dl className="mt-3 grid gap-3 border-t border-border pt-3 sm:grid-cols-2">
                {e.fields.map((f) => (
                  <div key={f.label}>
                    <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                      {f.label}
                    </dt>
                    <dd className="mt-1">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </details>
          </li>
        ))}
      </ul>
      <p className="text-xs text-muted-foreground">
        Only your actions on clients currently assigned to you are shown.
        Rebalances are simulated; no real trades are placed.
      </p>
    </div>
  );
}
