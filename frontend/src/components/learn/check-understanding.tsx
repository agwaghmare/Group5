import { useState } from "react";
import { CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { GradeResult, QuizQuestion } from "@/lib/learn-api";

export function CheckUnderstanding({
  questions,
  onSubmit,
  previous,
}: {
  questions: QuizQuestion[];
  onSubmit: (answers: Record<string, number>) => Promise<GradeResult>;
  previous?: { correct: number; total: number } | null;
}) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [result, setResult] = useState<GradeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const complete = questions.every((qn) => answers[qn.id] !== undefined);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await onSubmit(answers));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not grade");
    } finally {
      setBusy(false);
    }
  };

  const graded = (id: string) => result?.questions.find((g) => g.id === id);

  return (
    <section className="rounded-2xl border border-border p-5">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="font-display text-lg font-bold">
          Check my understanding
        </h3>
        {previous && !result && (
          <span className="text-xs text-muted-foreground">
            Last time: {previous.correct}/{previous.total}
          </span>
        )}
      </div>
      <div className="space-y-6">
        {questions.map((qn, qi) => {
          const g = graded(qn.id);
          return (
            <fieldset key={qn.id} className="space-y-2">
              <legend className="mb-2 font-medium">
                {qi + 1}. {qn.prompt}
              </legend>
              {qn.choices.map((choice, ci) => {
                const chosen = answers[qn.id] === ci;
                const isAnswer = g?.answer_index === ci;
                const tone = g
                  ? isAnswer
                    ? "border-primary bg-primary/10"
                    : chosen
                      ? "border-destructive/60 bg-destructive/10"
                      : "border-border"
                  : chosen
                    ? "border-primary bg-primary/10"
                    : "border-border hover:bg-accent";
                return (
                  <label
                    key={ci}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 text-sm ${tone}`}
                  >
                    <input
                      type="radio"
                      name={qn.id}
                      className="mt-1 accent-[var(--primary)]"
                      disabled={!!result}
                      checked={chosen}
                      onChange={() => setAnswers({ ...answers, [qn.id]: ci })}
                    />
                    <span className="flex-1">{choice}</span>
                    {g && isAnswer && (
                      <CheckCircle2
                        className="size-4 text-primary"
                        aria-label="Correct answer"
                      />
                    )}
                    {g && chosen && !isAnswer && (
                      <XCircle
                        className="size-4 text-destructive"
                        aria-label="Your answer"
                      />
                    )}
                  </label>
                );
              })}
              {g && (
                <p className="rounded-xl bg-card p-3 text-sm text-muted-foreground">
                  {g.correct ? "Right. " : "Not quite. "}
                  {g.explanation.learner}
                </p>
              )}
            </fieldset>
          );
        })}
      </div>
      {error && <p className="mt-4 text-sm text-destructive">{error}</p>}
      {result?.reward && <p role="status" className="mt-4 rounded-xl bg-primary/10 p-3 text-sm">
        {result.reward.awarded > 0 ? `You earned ${result.reward.awarded.toFixed(1)} PNC coins!`
          : result.reward.already_earned ? "You already earned this lesson's reward. Keep practicing!"
          : "Score at least 80% to earn this lesson's 0.1 PNC coins. Try again!"}
        {" "}Balance: {result.reward.balance.toFixed(1)} PNC coins.
      </p>}
      <div className="mt-5 flex items-center gap-4">
        {!result ? (
          <Button onClick={() => void submit()} disabled={!complete || busy}>
            {busy ? "Checking…" : "Check my answers"}
          </Button>
        ) : (
          <>
            <p className="font-display text-lg font-bold">
              {result.correct}/{result.total} correct
            </p>
            <Button
              variant="outline"
              onClick={() => {
                setResult(null);
                setAnswers({});
              }}
            >
              Try again
            </Button>
          </>
        )}
      </div>
    </section>
  );
}
