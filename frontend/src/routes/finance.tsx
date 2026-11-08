import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FinpilotHeader } from "@/components/finpilot-header";
import { FinanceSection, type FinanceView } from "@/components/finance/finance-section";

type FinanceSearch = {
  view?: FinanceView | undefined;
};

const VIEWS: FinanceView[] = ["money", "bills", "goals", "health"];

export const Route = createFileRoute("/finance")({
  validateSearch: (search: Record<string, unknown>): FinanceSearch => {
    const view = search["view"];
    // Map old tab names so bookmarked URLs still work
    const legacy: Record<string, FinanceView> = {
      overview: "money",
      cash: "money",
      debt: "health",
      whatif: "health",
    };
    if (typeof view === "string" && view in legacy) return { view: legacy[view] };
    return {
      view: VIEWS.includes(view as FinanceView) ? (view as FinanceView) : undefined,
    };
  },
  head: () => ({
    meta: [
      { title: "Finance — FINPILOT" },
      {
        name: "description",
        content: "Your money at a glance — safe spend, accounts, bills, goals and financial health.",
      },
      { property: "og:title", content: "Finance — FINPILOT" },
      {
        property: "og:description",
        content: "Your money at a glance — safe spend, accounts, bills, goals and financial health.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: FinancePage,
});

function FinancePage() {
  const { view = "money" } = Route.useSearch();
  const navigate = useNavigate({ from: "/finance" });

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader miniWheel />
      <main className="fifth-page-enter flex min-h-0 flex-1 flex-col overflow-y-auto rounded-[2rem] border border-border px-6 py-8 md:px-12 lg:px-16">
        <div className="mb-2 flex flex-wrap items-start justify-between gap-3">
          <p className="font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
            Personal finance
          </p>
        </div>
        <h1 className="font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
          Make money make sense.
        </h1>
        <p className="mt-3 max-w-xl text-muted-foreground">
          A complete view of your money, backed by transparent calculations.
        </p>
        <div className="mt-8 min-h-0 flex-1">
          <FinanceSection
            view={view}
            onViewChange={(v) =>
              void navigate({ search: (prev) => ({ ...prev, view: v }), replace: false })
            }
          />
        </div>
      </main>
    </div>
  );
}
