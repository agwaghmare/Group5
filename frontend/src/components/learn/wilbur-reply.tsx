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
      {reply.sources && reply.sources.length > 0 && <div className="space-y-2 border-t border-border pt-3">
        <p className="text-xs font-bold">Web sources</p>
        {reply.sources.map((source) => <a key={source.url} className="block text-sm text-primary underline"
          href={source.url} target="_blank" rel="noopener noreferrer">{source.title} — {source.publisher}</a>)}
      </div>}
      {reply.web_status === "unavailable" && <p className="text-xs text-muted-foreground">General explanation: the live web lookup did not return a source.</p>}
      {reply.google_search_url && <a className="inline-block text-xs text-primary underline" href={reply.google_search_url}
        target="_blank" rel="noopener noreferrer">Search this topic on Google</a>}
    </section>
  );
}
