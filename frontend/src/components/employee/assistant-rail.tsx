import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { staffFetch } from "@/lib/staff-api";

interface Reply {
  answer: string;
  reasons?: string[];
  citations?: { id: string; path: string; value: unknown; display?: string }[];
}

export function AssistantRail({
  featureId,
  resourceId,
  hint,
  agent = "bessie",
}: {
  featureId: string;
  resourceId?: string | undefined;
  hint: string;
  agent?: "bessie" | "wilbur";
}) {
  const name = agent === "wilbur" ? "Wilbur" : "Bessie";
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<(Reply & { question: string })[]>([]);
  const active = useRef<AbortController | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(
    () => () => {
      const request = active.current;
      active.current = null;
      request?.abort();
      clearTimeout(timer.current);
    },
    [],
  );

  const ask = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || active.current) return;
    const controller = new AbortController();
    active.current = controller;
    setPending(true);
    setError(null);
    timer.current = setTimeout(() => controller.abort(), 25_000);
    try {
      const reply = await staffFetch<Reply>("/assistant", {
        body: {
          feature_id: featureId,
          resource_id: resourceId,
          agent,
          question: trimmed,
        },
        signal: controller.signal,
      });
      if (active.current !== controller) return;
      setTurns((current) => [...current, { ...reply, question: trimmed }]);
      setQuestion("");
    } catch (err) {
      if (active.current !== controller) return;
      setError(
        controller.signal.aborted
          ? `${name} took too long. Please try again.`
          : err instanceof Error
            ? err.message
            : "Something went wrong.",
      );
    } finally {
      if (active.current === controller) {
        clearTimeout(timer.current);
        active.current = null;
        setPending(false);
      }
    }
  };

  const prompts = resourceId
    ? [
        "Why does this need review?",
        "What is missing?",
        "What would change the outcome?",
      ]
    : ["Hi", "What can you help me with?", "Explain my workspace"];

  return (
    <aside className="flex h-full w-full flex-col border-border bg-background p-4 lg:w-80 lg:border-l">
      <p className="font-display text-lg font-extrabold">{name}</p>
      <p className="text-xs text-muted-foreground">
        {agent === "wilbur"
          ? "Plain-language explanations, within your role."
          : "Your employee copilot."}
      </p>
      <p className="mt-2 text-xs text-muted-foreground">{hint}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {prompts.map((prompt) => (
          <button
            key={prompt}
            type="button"
            disabled={pending}
            className="rounded-full border border-border px-3 py-1 text-left text-xs hover:border-primary disabled:opacity-50"
            onClick={() => void ask(prompt)}
          >
            {prompt}
          </button>
        ))}
      </div>
      <div
        className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto"
        aria-live="polite"
      >
        {turns.length === 0 && (
          <p className="text-sm text-muted-foreground">How can I help?</p>
        )}
        {turns.map((turn, index) => (
          <article
            key={index}
            className="rounded-2xl border border-border p-3 text-sm"
          >
            <p className="font-display font-bold">{turn.question}</p>
            <p className="mt-1 whitespace-pre-wrap text-muted-foreground">
              {turn.answer}
            </p>
            {!!turn.reasons?.length && (
              <ul className="mt-2 list-inside list-disc text-muted-foreground">
                {turn.reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            )}
            {!!turn.citations?.length && (
              <details className="mt-2 text-xs text-muted-foreground">
                <summary>Evidence</summary>
                <ul>
                  {turn.citations.map((citation) => (
                    <li key={citation.id}>
                      {citation.path}:{" "}
                      {citation.display ?? String(citation.value)}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </article>
        ))}
        {pending && (
          <p role="status" className="text-sm text-muted-foreground">
            {name} is thinking…
          </p>
        )}
      </div>
      <form
        className="mt-3 flex flex-col gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void ask(question);
        }}
      >
        <Textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder={`Ask ${name}`}
          aria-label={`Ask ${name}`}
          rows={3}
        />
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={pending || !question.trim()}>
          {pending ? "Asking…" : `Ask ${name}`}
        </Button>
      </form>
    </aside>
  );
}
