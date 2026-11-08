import { useQuery } from "@tanstack/react-query";
import { FinpilotHeader } from "@/components/finpilot-header";
import { ROLE_LABEL, readStaffToken, staffFetch } from "@/lib/staff-api";
import type { FifthFrom } from "@/lib/fifth-page";

const RULES = [
  {
    label: "Code computes",
    body: "Utilization, debt-to-income, and the suggested next step are calculated in the app. The assistant cannot invent a figure.",
  },
  {
    label: "A person opens the file",
    body: "A credit file stays closed until someone chooses a purpose and confirms the application reference.",
  },
  {
    label: "A person records the outcome",
    body: "Proceed, ask for more information, refer to senior review, or decline. An override needs a reason. Nothing is sent.",
  },
];

const ROLE_LINE: Record<string, string> = {
  credit_analyst:
    "Your queue is blind. Senior review is a decision you record, not a file that leaves the desk.",
  service_specialist: "You see only the context the customer agreed to share.",
  marketing_analyst:
    "No audience is sent. Without consent records, the list stays empty.",
  portfolio_manager:
    "You see aggregates. Groups smaller than five stay hidden.",
  compliance_analyst:
    "You review overrides. You do not write the credit decision.",
  auditor: "You can read the audit trail. You cannot change a decision.",
  benefits_admin: "You publish benefit rules. You do not see a credit file.",
};

export function CenterBrief({
  from,
  onReturn,
}: {
  from: FifthFrom;
  onReturn: () => void;
}) {
  const staff = useQuery({
    queryKey: ["fifth", "staff"],
    enabled: from === "employee" && Boolean(readStaffToken()),
    queryFn: () =>
      staffFetch<{
        employee: { role: string; display_name: string };
        banner: string;
        features: string[];
      }>("/me"),
  });
  const decisions = useQuery({
    queryKey: ["fifth", "decisions"],
    enabled:
      from === "employee" &&
      Boolean(staff.data?.features.includes("staff.decision")),
    queryFn: () =>
      staffFetch<{
        decisions: {
          id: string;
          decision: string;
          rationale: string;
          override?: boolean;
          sent_externally?: boolean;
        }[];
        in_progress?: {
          id: string;
          decision: string;
          rationale: string;
          prospect_id?: string;
        }[];
      }>("/decisions"),
  });
  const role = staff.data?.employee.role;
  const draft = decisions.data?.in_progress?.[0];
  const recorded = decisions.data?.decisions?.[0];
  return (
    <div className="relative flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader
        miniWheel
        onWheelReturn={onReturn}
        role={role ? (ROLE_LABEL[role] ?? role) : undefined}
        badge={
          from === "login"
            ? "Before sign-in"
            : from === "employee"
              ? "Prototype data"
              : undefined
        }
      />
      <main className="fifth-page-enter flex min-h-0 flex-1 flex-col justify-start overflow-y-auto rounded-[2rem] border border-border px-8 py-8 md:px-20">
        <p className="mb-4 font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
          05 — The center
        </p>
        <h1 className="max-w-4xl font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
          The model never decides.
        </h1>
        <p className="mt-6 max-w-xl text-lg text-muted-foreground">
          {from === "employee"
            ? "This desk can recommend and explain. Only you can record what happens next."
            : "The wheel tabs are the work. The center is the rule this demo is graded on."}
        </p>
        <ol className="mt-10 grid max-w-4xl gap-4 md:grid-cols-3">
          {RULES.map((rule, index) => (
            <li
              key={rule.label}
              className="rounded-2xl border border-border p-4"
            >
              <p className="font-display text-sm font-bold uppercase tracking-wide text-primary">
                0{index + 1} — {rule.label}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">{rule.body}</p>
            </li>
          ))}
        </ol>
        {role && (
          <p className="mt-8 max-w-2xl text-sm text-foreground">
            {ROLE_LINE[role] ??
              "Your role sees only the records assigned to it."}
          </p>
        )}
        {draft && (
          <article className="mt-6 max-w-2xl rounded-2xl border border-primary/40 p-4">
            <p className="font-display text-sm font-bold uppercase text-primary">
              In progress{draft.prospect_id ? ` · ${draft.prospect_id}` : ""}
            </p>
            <p className="mt-2 font-display text-2xl font-bold">
              {draft.decision || "Decision not chosen yet"}
            </p>
            {draft.rationale && (
              <p className="mt-2 text-sm text-muted-foreground">
                {draft.rationale}
              </p>
            )}
          </article>
        )}
        {!draft && recorded && (
          <article className="mt-6 max-w-2xl rounded-2xl border border-border p-4">
            <p className="font-display text-sm font-bold uppercase text-primary">
              Latest recorded decision
            </p>
            <p className="mt-2 font-display text-2xl font-bold">
              {recorded.decision}
            </p>
            <p className="mt-2 text-sm text-muted-foreground">
              {recorded.rationale}
            </p>
            <p className="mt-3 text-xs uppercase tracking-wide text-muted-foreground">
              {recorded.override
                ? "Override flagged for review"
                : "Matches the suggestion"}
              {" · "}
              {recorded.sent_externally ? "Sent" : "Not sent"}
            </p>
          </article>
        )}
        {staff.data?.banner && (
          <p className="mt-8 text-xs text-muted-foreground">
            {staff.data.banner}
          </p>
        )}
      </main>
    </div>
  );
}
