import type { ExplainResult } from "@/lib/learn-api";

export function WilburReply({ reply }: { reply: ExplainResult["wilbur"] }) {
  if (!reply) return null;
  return (
    <section aria-label="Wilbur's explanation" className="space-y-3 rounded-2xl border border-primary/30 bg-primary/5 p-5">
      <h3 className="font-display text-lg font-bold">Wilbur</h3>
      <p className="whitespace-pre-line text-sm">{reply.answer}</p>
      {reply.reasons.length > 0 && <ul className="list-disc space-y-2 pl-5 text-sm">
        {reply.reasons.map((reason, index) => <li key={index}>{reason}</li>)}
      </ul>}
      {reply.limitations.map((limitation, index) => <p key={index} className="text-xs text-muted-foreground">{limitation}</p>)}
    </section>
  );
}
