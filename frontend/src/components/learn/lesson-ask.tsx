import { useEffect, useRef, useState } from "react";
import { ArrowUp, Mic, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ExplanationCard } from "@/components/learn/explanation-card";
import { learnApi, learnUserId, type ExplainResult } from "@/lib/learn-api";

type SpeechRec = {
  lang: string;
  interimResults: boolean;
  onresult: ((ev: { results: ArrayLike<ArrayLike<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
};

function createRecognition(): SpeechRec | null {
  if (typeof window === "undefined") return null;
  const host = window as unknown as {
    SpeechRecognition?: new () => SpeechRec;
    webkitSpeechRecognition?: new () => SpeechRec;
  };
  const Ctor = host.SpeechRecognition ?? host.webkitSpeechRecognition;
  return Ctor ? new Ctor() : null;
}

/** Ask about the open lesson by typing or speaking. Answers come from the Learn API. */
export function LessonAsk({
  lessonId,
  lessonTitle,
  onOpenLesson,
}: {
  lessonId: string;
  lessonTitle: string;
  onOpenLesson: (lessonId: string) => void;
}) {
  const suggestions = [
    `Explain ${lessonTitle} in simple terms`,
    "How does this affect monthly cash flow?",
    "Give me a small example",
  ];
  const [draft, setDraft] = useState("");
  const [listening, setListening] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ExplainResult | null>(null);
  const [micReady, setMicReady] = useState(false);
  const recRef = useRef<SpeechRec | null>(null);

  useEffect(() => {
    setMicReady(createRecognition() !== null);
    return () => recRef.current?.stop();
  }, []);

  const ask = async (question: string) => {
    const text = question.trim();
    if (!text || busy) return;
    setDraft(text);
    setBusy(true);
    setError(null);
    try {
      setResult(
        await learnApi.explain({
          question: text,
          user_id: learnUserId(),
          lesson_id: lessonId,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not answer that");
    } finally {
      setBusy(false);
    }
  };

  const toggleMic = () => {
    if (listening) {
      recRef.current?.stop();
      setListening(false);
      return;
    }
    const rec = createRecognition();
    if (!rec) {
      setError("This browser does not support speech recognition. Type your question instead.");
      return;
    }
    rec.lang = "en-US";
    rec.interimResults = false;
    rec.onresult = (ev) => {
      const said = ev.results[0]?.[0]?.transcript ?? "";
      if (said) setDraft(said);
    };
    rec.onerror = () => setListening(false);
    rec.onend = () => setListening(false);
    recRef.current = rec;
    setError(null);
    try {
      rec.start();
      setListening(true);
    } catch {
      setListening(false);
      setError("The microphone could not start. Type your question instead.");
    }
  };

  return (
    <section className="space-y-4 rounded-2xl border border-border bg-card/40 p-5">
      <div>
        <p className="font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
          Ask about this lesson
        </p>
        <h2 className="mt-2 font-display text-2xl font-extrabold">A little clarity. Just ask.</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Type or speak a question about this lesson. The answer stays inside this lesson set.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {suggestions.map((prompt) => (
          <button
            key={prompt}
            type="button"
            onClick={() => void ask(prompt)}
            className="rounded-full border border-border px-3 py-1.5 text-left text-sm text-foreground transition-colors hover:bg-accent"
          >
            {prompt}
          </button>
        ))}
      </div>

      <form
        className="flex items-end gap-2 rounded-2xl border border-border bg-background p-2"
        onSubmit={(ev) => {
          ev.preventDefault();
          void ask(draft);
        }}
      >
        <Textarea
          value={draft}
          onChange={(ev) => setDraft(ev.target.value)}
          placeholder={`Explain ${lessonTitle} in simple terms`}
          rows={2}
          className="min-h-[52px] flex-1 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
          aria-label={`Question about ${lessonTitle}`}
          onKeyDown={(ev) => {
            if (ev.key === "Enter" && !ev.shiftKey) {
              ev.preventDefault();
              void ask(draft);
            }
          }}
        />
        <Button
          type="button"
          variant={listening ? "default" : "outline"}
          size="icon"
          className="shrink-0 rounded-full"
          aria-pressed={listening}
          aria-label={listening ? "Stop microphone" : "Speak a question"}
          disabled={!micReady && !listening}
          onClick={toggleMic}
        >
          {listening ? <Square aria-hidden="true" /> : <Mic aria-hidden="true" />}
        </Button>
        <Button
          type="submit"
          size="icon"
          className="shrink-0 rounded-full"
          disabled={busy || !draft.trim()}
          aria-label="Send question"
        >
          <ArrowUp aria-hidden="true" />
        </Button>
      </form>
      {!micReady && (
        <p className="text-xs text-muted-foreground">
          The microphone needs a browser with speech recognition, such as Chrome or Safari.
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {busy && <p className="text-sm text-muted-foreground">Thinking…</p>}
      {result && (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-display text-xl font-bold">{result.label ?? "Answer"}</h3>
            {result.lesson_id && (
              <Button
                variant="link"
                className="h-auto px-0 text-primary"
                onClick={() => onOpenLesson(result.lesson_id!)}
              >
                Open lesson: {result.lesson_title}
              </Button>
            )}
          </div>
          <ExplanationCard
            key={result.question_id ?? result.label ?? "ask"}
            explanation={result.explanation}
            onGoDeeper={async () => {
              const deep = await learnApi.explain({
                question_id: result.question_id,
                question: result.question_id ? undefined : draft,
                user_id: learnUserId(),
                lesson_id: lessonId,
                go_deeper: true,
              });
              return deep.explanation.go_deeper;
            }}
          />
          {result.notes.map((note) => (
            <p key={note} className="text-xs text-muted-foreground">
              {note}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}
