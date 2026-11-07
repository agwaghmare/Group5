import { useState } from "react";
import { ChevronDown, ChevronUp, Lightbulb, Sigma } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Explanation, GoDeeper } from "@/lib/learn-api";

/**
 * Renders the Skill.md Section 6 sequence exactly as the backend orders it:
 * one sentence → analogy → worked example → what this means for you → safe next step → go deeper.
 * "Check my understanding" is rendered by the caller so lessons and Explain-this can place it differently.
 */
export function ExplanationCard({
  explanation,
  onGoDeeper,
}: {
  explanation: Explanation;
  onGoDeeper?: () => Promise<GoDeeper>;
}) {
  const [deeper, setDeeper] = useState<GoDeeper>(explanation.go_deeper);
  const [loading, setLoading] = useState(false);
  const example = explanation.worked_example;

  const toggleDeeper = async () => {
    if (deeper.expanded) {
      setDeeper({ ...deeper, expanded: false });
      return;
    }
    if (deeper.detail) {
      setDeeper({ ...deeper, expanded: true });
      return;
    }
    if (!onGoDeeper) return;
    setLoading(true);
    try {
      setDeeper(await onGoDeeper());
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <p className="text-xl leading-relaxed text-foreground md:text-2xl">
        {explanation.one_sentence}
      </p>

      <div className="flex gap-3 rounded-2xl border border-border bg-card p-4">
        <Lightbulb
          className="mt-0.5 size-5 shrink-0 text-primary"
          aria-hidden="true"
        />
        <p className="text-muted-foreground">{explanation.analogy}</p>
      </div>

      <section className="rounded-2xl border border-border p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-bold">{example.title}</h3>
          <Badge
            variant={example.label === "your numbers" ? "default" : "secondary"}
          >
            {example.label}
          </Badge>
        </div>
        <ol className="space-y-2 text-sm md:text-base">
          {example.steps.map((step, i) => (
            <li key={i} className="flex gap-3">
              <span className="font-display text-xs font-bold text-primary">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
        {example.result && (
          <p className="mt-4 font-semibold text-primary">{example.result}</p>
        )}
        <p className="mt-3 text-xs text-muted-foreground">
          {example.disclaimer}
        </p>
      </section>

      <section className="rounded-2xl bg-primary/10 p-5">
        <p className="mb-1 font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
          What this means for you
        </p>
        <p>{explanation.what_this_means_for_you}</p>
        <p className="mt-3 text-sm">
          <span className="font-semibold">One safe next step: </span>
          {explanation.safe_next_step}
        </p>
      </section>

      <section>
        <Button
          variant="outline"
          onClick={() => void toggleDeeper()}
          disabled={loading || (!deeper.detail && !onGoDeeper)}
        >
          <Sigma aria-hidden="true" />
          {deeper.expanded
            ? "Hide the math"
            : loading
              ? "Loading…"
              : "Go deeper"}
          {deeper.expanded ? (
            <ChevronUp aria-hidden="true" />
          ) : (
            <ChevronDown aria-hidden="true" />
          )}
        </Button>
        {deeper.expanded && (
          <div className="mt-4 space-y-4 rounded-2xl border border-border bg-card p-5 text-sm">
            {deeper.symbols && deeper.symbols.length > 0 && (
              <div>
                <p className="mb-2 font-display text-xs font-bold uppercase tracking-[0.3em] text-muted-foreground">
                  Symbols
                </p>
                <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                  {deeper.symbols.map((s) => (
                    <li key={s}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
            {deeper.detail && (
              <p className="leading-relaxed">{deeper.detail}</p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
