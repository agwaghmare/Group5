import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCustomerSession } from "@/lib/customer-session";
import { WilburReply } from "@/components/learn/wilbur-reply";
import { Badge } from "@/components/ui/badge";
import { ExplanationCard } from "@/components/learn/explanation-card";
import { learnApi, learnUserId, type ExplainResult } from "@/lib/learn-api";

/**
 * "Learn from the current decision": use the signed-in customer's tracker
 * and click a question such as "Explain APY" or "What is credit utilization?".
 * Numbers come from the synthetic tracker; nothing here is an offer.
 */
export function ExplainThis({
  onOpenLesson,
}: {
  onOpenLesson: (lessonId: string) => void;
}) {
  const session = useCustomerSession();
  const [usePersonal, setUsePersonal] = useState(true);
  const [question, setQuestion] = useState("");
  const trackerId = session?.customerId && !session.isStaff ? Number(session.customerId) : undefined;
  const personalAvailable = Boolean(session?.token && trackerId !== undefined && Number.isInteger(trackerId));
  const appliedTracker = usePersonal && personalAvailable ? trackerId : undefined;
  const requestId = useRef(0);
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const prompts = useQuery({
    queryKey: ["learn", "prompts", session?.email, session?.token, appliedTracker],
    queryFn: () => learnApi.prompts(undefined, appliedTracker),
    retry: false,
  });

  useEffect(() => {
    requestId.current += 1;
    setResult(null);
    setError(null);
    setBusy(null);
  }, [session?.token, appliedTracker]);

  const ask = async (questionId?: string, text?: string) => {
    if (busy !== null) return;
    const currentRequest = ++requestId.current;
    setBusy(questionId ?? "custom");
    setResult(null);
    setError(null);
    try {
      const response = await learnApi.explain({
          question_id: questionId,
          question: text,
          tracker_user_id: appliedTracker,
          user_id: learnUserId(),
        });
      if (currentRequest === requestId.current) setResult(response);
    } catch (e) {
      if (currentRequest === requestId.current) setError(e instanceof Error ? e.message : "Could not explain");
    } finally {
      if (currentRequest === requestId.current) setBusy(null);
    }
  };


  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <aside className="space-y-5">
        <div className="rounded-2xl border border-border p-4">
          <p className="mb-3 font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
            Whose numbers?
          </p>
          <p className="text-sm text-muted-foreground">
            {appliedTracker !== undefined
              ? `Your signed-in finance tracker (${appliedTracker}). Wilbur explains your own synthetic numbers.`
              : "Sample lesson numbers. Sign in to a customer account to use your own tracker."}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant={usePersonal && personalAvailable ? "default" : "outline"}
              disabled={!personalAvailable || busy !== null} onClick={() => setUsePersonal(true)}>
              Use my numbers
            </Button>
            <Button variant={!usePersonal || !personalAvailable ? "default" : "outline"}
              disabled={busy !== null} onClick={() => setUsePersonal(false)}>
              Use sample numbers
            </Button>
          </div>
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
        <form className="mb-5 space-y-3 rounded-2xl border border-border p-4" onSubmit={(event) => {
          event.preventDefault();
          if (question.trim()) void ask(undefined, question.trim());
        }}>
          <label htmlFor="wilbur-question" className="font-display font-bold">Ask Wilbur</label>
          <Input id="wilbur-question" value={question} onChange={(event) => setQuestion(event.target.value)}
            placeholder="Explain annual percentage yield in plain words" disabled={busy !== null} />
          <Button type="submit" disabled={busy !== null || !question.trim()}>
            {busy === "custom" ? "Wilbur is thinking..." : "Ask Wilbur"}
          </Button>
        </form>
        {error && <p className="mb-4 text-sm text-destructive">{error}</p>}
        {!result && !error && (
          <div className="flex h-full min-h-[280px] items-center justify-center rounded-2xl border border-dashed border-border p-8 text-center text-muted-foreground">
            Ask Wilbur or pick a question on the left. Start with a plain-word
            explanation, then explore the worked example.
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
            <WilburReply reply={result.wilbur} />
            <ExplanationCard
              key={result.question_id ?? "unmatched"}
              explanation={result.explanation}
              onGoDeeper={async () => {
                const deep = await learnApi.explain({
                  question_id: result.question_id,
                  question: result.question_id ? undefined : question,
                  tracker_user_id: appliedTracker,
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
