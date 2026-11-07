import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { ExplanationCard } from "@/components/learn/explanation-card";
import { learnApi, learnUserId, type ExplainResult } from "@/lib/learn-api";

/**
 * "Learn from the current decision": pick a Toyota pack customer (or a tracker user)
 * and click a question such as "Explain this APR" or "What is residual value?".
 * Numbers come from that synthetic contract; nothing here is an offer.
 */
export function ExplainThis({
  onOpenLesson,
}: {
  onOpenLesson: (lessonId: string) => void;
}) {
  const [customerId, setCustomerId] = useState("C001");
  const [trackerId, setTrackerId] = useState("");
  const [applied, setApplied] = useState<{
    customer: string | undefined;
    tracker: number | undefined;
  }>({
    customer: "C001",
    tracker: undefined,
  });
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const prompts = useQuery({
    queryKey: ["learn", "prompts", applied.customer, applied.tracker],
    queryFn: () => learnApi.prompts(applied.customer, applied.tracker),
  });

  const ask = async (questionId: string) => {
    setBusy(questionId);
    setError(null);
    try {
      setResult(
        await learnApi.explain({
          question_id: questionId,
          customer_id: applied.customer,
          tracker_user_id: applied.tracker,
          user_id: learnUserId(),
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not explain");
    } finally {
      setBusy(null);
    }
  };

  const apply = () => {
    const tracker = trackerId.trim() ? Number(trackerId) : undefined;
    setApplied({
      customer: customerId.trim() || undefined,
      tracker: Number.isFinite(tracker) ? tracker : undefined,
    });
    setResult(null);
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <aside className="space-y-5">
        <div className="rounded-2xl border border-border p-4">
          <p className="mb-3 font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
            Whose numbers?
          </p>
          <label
            className="mb-1 block text-xs text-muted-foreground"
            htmlFor="learn-customer"
          >
            Toyota pack customer (C001–C020)
          </label>
          <Input
            id="learn-customer"
            value={customerId}
            onChange={(e) => setCustomerId(e.target.value.toUpperCase())}
            placeholder="C001"
          />
          <label
            className="mb-1 mt-3 block text-xs text-muted-foreground"
            htmlFor="learn-tracker"
          >
            Finance tracker user (1000–1499, optional)
          </label>
          <Input
            id="learn-tracker"
            value={trackerId}
            onChange={(e) => setTrackerId(e.target.value)}
            placeholder="1000"
            inputMode="numeric"
          />
          <Button className="mt-3 w-full" variant="secondary" onClick={apply}>
            Use these numbers
          </Button>
          {prompts.data?.notes.map((n) => (
            <p key={n} className="mt-3 text-xs text-muted-foreground">
              {n}
            </p>
          ))}
        </div>

        <div className="rounded-2xl border border-border p-4">
          <p className="mb-3 font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
            Explain this
          </p>
          {prompts.isLoading && (
            <p className="text-sm text-muted-foreground">Loading questions…</p>
          )}
          {prompts.error && (
            <p className="text-sm text-destructive">
              {(prompts.error as Error).message}
            </p>
          )}
          <div className="flex flex-col gap-2">
            {prompts.data?.prompts.map((p) => (
              <Button
                key={p.id}
                variant={p.highlighted ? "default" : "outline"}
                className="h-auto justify-start whitespace-normal py-2 text-left"
                disabled={busy !== null}
                onClick={() => void ask(p.id)}
              >
                {busy === p.id ? "Thinking…" : p.label}
              </Button>
            ))}
          </div>
        </div>
      </aside>

      <div>
        {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
        {!result && !error && (
          <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-border p-8 text-center text-muted-foreground">
            Pick a question on the left. The answer uses that customer's
            synthetic contract, in plain words first.
          </div>
        )}
        {result && (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="font-display text-2xl font-extrabold md:text-3xl">
                {result.label ?? "Explanation"}
              </h2>
              {result.lesson_id && (
                <Button
                  variant="link"
                  className="px-0 text-primary"
                  onClick={() => onOpenLesson(result.lesson_id!)}
                >
                  Open lesson: {result.lesson_title}
                </Button>
              )}
            </div>
            <ExplanationCard
              key={result.question_id ?? "unmatched"}
              explanation={result.explanation}
              onGoDeeper={async () => {
                const deep = await learnApi.explain({
                  question_id: result.question_id,
                  customer_id: applied.customer,
                  tracker_user_id: applied.tracker,
                  go_deeper: true,
                });
                return deep.explanation.go_deeper;
              }}
            />
            {result.your_numbers && (
              <details className="rounded-2xl border border-border p-4 text-sm">
                <summary className="cursor-pointer font-medium">
                  Numbers used
                </summary>
                <div className="mt-3 flex flex-wrap gap-2">
                  {Object.entries({
                    ...result.your_numbers.contract,
                    ...result.your_numbers.tracker,
                  }).map(([k, v]) => (
                    <Badge key={k} variant="secondary" className="font-normal">
                      {k}: {String(v)}
                    </Badge>
                  ))}
                </div>
              </details>
            )}
            {result.notes.map((n) => (
              <p key={n} className="text-xs text-muted-foreground">
                {n}
              </p>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
