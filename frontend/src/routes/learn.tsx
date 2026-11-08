import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { FinpilotHeader } from "@/components/finpilot-header";
import { RequireCustomer } from "@/components/require-customer";
import { LearnSection, type LearnView } from "@/components/learn/learn-section";

type LearnSearch = {
  view?: LearnView | undefined;
  lesson?: string | undefined;
};

const VIEWS: LearnView[] = ["lessons", "map", "explain"];

export const Route = createFileRoute("/learn")({
  validateSearch: (search: Record<string, unknown>): LearnSearch => {
    const view = search["view"];
    const lesson = search["lesson"];
    return {
      view: VIEWS.includes(view as LearnView) ? (view as LearnView) : undefined,
      lesson: typeof lesson === "string" && lesson ? lesson : undefined,
    };
  },
  head: () => ({
    meta: [
      { title: "Learn — FINPILOT" },
      {
        name: "description",
        content:
          "Short lessons, a knowledge map, and plain-word explanations of your own numbers.",
      },
      { property: "og:title", content: "Learn — FINPILOT" },
      {
        property: "og:description",
        content:
          "Short lessons, a knowledge map, and plain-word explanations of your own numbers.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: LearnPage,
});

function LearnPage() {
  const { view = "lessons", lesson = null } = Route.useSearch();
  const navigate = useNavigate({ from: "/learn" });
  const setSearch = (next: LearnSearch) =>
    void navigate({ search: (prev) => ({ ...prev, ...next }), replace: false });

  return (
    <RequireCustomer>
    <div className="flex h-dvh flex-col overflow-hidden bg-background p-4 md:p-6">
      <FinpilotHeader miniWheel />
      <main className="fifth-page-enter flex min-h-0 flex-1 flex-col overflow-y-auto rounded-[2rem] border border-border px-6 py-8 md:px-14">
        <p className="mb-2 font-display text-sm font-bold uppercase tracking-[0.3em] text-primary">
          04 — Learn
        </p>
        <h1 className="mb-6 font-display text-4xl font-extrabold leading-[0.95] md:text-6xl">
          Learn it in plain words.
        </h1>
        <LearnSection
          view={view}
          lessonId={lesson}
          onViewChange={(v) => setSearch({ view: v })}
          onLessonChange={(id) => setSearch({ lesson: id ?? undefined })}
        />
      </main>
    </div>
    </RequireCustomer>
  );
}
