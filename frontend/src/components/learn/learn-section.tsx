import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Clock,
  Lock,
  Map as MapIcon,
  MessageCircleQuestion,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CheckUnderstanding } from "@/components/learn/check-understanding";
import { ExplainThis } from "@/components/learn/explain-this";
import { ExplanationCard } from "@/components/learn/explanation-card";
import { KnowledgeMapView } from "@/components/learn/knowledge-map";
import { learnApi, learnUserId, type LessonSummary } from "@/lib/learn-api";

export type LearnView = "lessons" | "map" | "explain";

/** The Learn tab (Wilbur). Two views, Lessons and Knowledge Map, plus Explain-this for the current decision. */
export function LearnSection({
  view,
  lessonId,
  onViewChange,
  onLessonChange,
}: {
  view: LearnView;
  lessonId: string | null;
  onViewChange: (v: LearnView) => void;
  onLessonChange: (id: string | null) => void;
}) {
  const [userId, setUserId] = useState("local");
  useEffect(() => setUserId(learnUserId()), []);

  const openLesson = (id: string) => {
    onLessonChange(id);
    onViewChange("lessons");
  };

  return (
    <Tabs
      value={view}
      onValueChange={(v) => onViewChange(v as LearnView)}
      className="flex min-h-0 flex-1 flex-col"
    >
      <TabsList className="mb-6 w-fit">
        <TabsTrigger value="lessons">
          <BookOpen aria-hidden="true" /> Lessons
        </TabsTrigger>
        <TabsTrigger value="map">
          <MapIcon aria-hidden="true" /> Knowledge Map
        </TabsTrigger>
        <TabsTrigger value="explain">
          <MessageCircleQuestion aria-hidden="true" /> Explain this
        </TabsTrigger>
      </TabsList>

      <TabsContent value="lessons" className="min-h-0 flex-1">
        {lessonId ? (
          <LessonDetail
            lessonId={lessonId}
            userId={userId}
            onBack={() => onLessonChange(null)}
            onOpenLesson={openLesson}
          />
        ) : (
          <LessonsList userId={userId} onOpen={openLesson} />
        )}
      </TabsContent>

      <TabsContent value="map" className="min-h-0 flex-1">
        <MapTab
          userId={userId}
          selected={lessonId}
          onOpen={openLesson}
          onSelect={onLessonChange}
        />
      </TabsContent>

      <TabsContent value="explain" className="min-h-0 flex-1">
        <ExplainThis onOpenLesson={openLesson} />
      </TabsContent>
    </Tabs>
  );
}

function StatusBadge({ status }: { status: LessonSummary["status"] }) {
  if (status === "completed") return <Badge>Done</Badge>;
  if (status === "locked")
    return (
      <Badge variant="secondary">
        <Lock className="size-3" aria-hidden="true" /> Locked
      </Badge>
    );
  return <Badge variant="outline">Ready</Badge>;
}

function LessonsList({
  userId,
  onOpen,
}: {
  userId: string;
  onOpen: (id: string) => void;
}) {
  const topics = useQuery({
    queryKey: ["learn", "topics"],
    queryFn: learnApi.topics,
  });
  const lessons = useQuery({
    queryKey: ["learn", "lessons", userId],
    queryFn: () => learnApi.lessons(userId),
  });
  const progress = useQuery({
    queryKey: ["learn", "progress", userId],
    queryFn: () => learnApi.progress(userId),
  });

  if (lessons.error || topics.error) {
    return <ApiError error={(lessons.error ?? topics.error) as Error} />;
  }
  if (!lessons.data || !topics.data)
    return <p className="text-muted-foreground">Loading lessons…</p>;

  const recommended = progress.data?.recommended_lesson_id ?? null;
  const done = progress.data?.completed_lessons.length ?? 0;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-muted-foreground">
          {done} of {lessons.data.lessons.length} lessons done.
          {recommended && (
            <>
              {" "}
              Next up:{" "}
              <Button
                variant="link"
                className="h-auto p-0 text-primary"
                onClick={() => onOpen(recommended)}
              >
                {lessons.data.lessons.find((l) => l.id === recommended)
                  ?.title ?? recommended}
              </Button>
            </>
          )}
        </p>
      </div>
      {topics.data.topics.map((t) => {
        const rows = lessons.data.lessons.filter((l) => l.topic_id === t.id);
        if (rows.length === 0) return null;
        return (
          <section key={t.id}>
            <h2 className="font-display text-xl font-bold">{t.title}</h2>
            <p className="mb-3 text-sm text-muted-foreground">{t.summary}</p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {rows.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  onClick={() => onOpen(l.id)}
                  className={`flex flex-col items-start gap-2 rounded-2xl border p-4 text-left transition-colors hover:bg-accent ${
                    l.id === recommended ? "border-primary" : "border-border"
                  }`}
                >
                  <div className="flex w-full items-center justify-between gap-2">
                    <StatusBadge status={l.status} />
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="size-3" aria-hidden="true" />{" "}
                      {l.minutes} min
                    </span>
                  </div>
                  <span className="font-display font-bold leading-tight">
                    {l.title}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {l.summary}
                  </span>
                </button>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function LessonDetail({
  lessonId,
  userId,
  onBack,
  onOpenLesson,
}: {
  lessonId: string;
  userId: string;
  onBack: () => void;
  onOpenLesson: (id: string) => void;
}) {
  const qc = useQueryClient();
  const lesson = useQuery({
    queryKey: ["learn", "lesson", lessonId, userId],
    queryFn: () => learnApi.lesson(lessonId, userId),
  });
  const all = useQuery({
    queryKey: ["learn", "lessons", userId],
    queryFn: () => learnApi.lessons(userId),
  });

  if (lesson.error) return <ApiError error={lesson.error as Error} />;
  if (!lesson.data)
    return <p className="text-muted-foreground">Loading lesson…</p>;
  const l = lesson.data;
  const titleOf = (id: string) =>
    all.data?.lessons.find((x) => x.id === id)?.title ?? id;
  const questions = l.explanation.check_my_understanding?.questions ?? [];

  return (
    <article className="mx-auto max-w-3xl space-y-8 pb-12">
      <div>
        <Button variant="ghost" className="-ml-3 mb-3" onClick={onBack}>
          <ArrowLeft aria-hidden="true" /> All lessons
        </Button>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={l.status} />
          <span className="flex items-center gap-1 text-xs text-muted-foreground">
            <Clock className="size-3" aria-hidden="true" /> {l.minutes} min
          </span>
        </div>
        <h1 className="font-display text-3xl font-extrabold md:text-5xl">
          {l.title}
        </h1>
        {l.prerequisites.length > 0 && (
          <p className="mt-3 text-sm text-muted-foreground">
            Builds on:{" "}
            {l.prerequisites.map((p, i) => (
              <span key={p}>
                {i > 0 && ", "}
                <Button
                  variant="link"
                  className="h-auto p-0 text-primary"
                  onClick={() => onOpenLesson(p)}
                >
                  {titleOf(p)}
                </Button>
              </span>
            ))}
          </p>
        )}
      </div>

      <ExplanationCard
        key={l.id}
        explanation={l.explanation}
        onGoDeeper={() => learnApi.goDeeper(l.id, userId)}
      />

      {questions.length > 0 && (
        <CheckUnderstanding
          key={l.id}
          questions={questions}
          previous={l.check_my_understanding_result}
          onSubmit={async (answers) => {
            const res = await learnApi.checkUnderstanding(
              l.id,
              userId,
              answers,
            );
            await qc.invalidateQueries({ queryKey: ["learn"] });
            return res;
          }}
        />
      )}
    </article>
  );
}

function MapTab({
  userId,
  selected,
  onOpen,
  onSelect,
}: {
  userId: string;
  selected: string | null;
  onOpen: (id: string) => void;
  onSelect: (id: string | null) => void;
}) {
  const map = useQuery({
    queryKey: ["learn", "map", userId],
    queryFn: () => learnApi.map(userId),
  });
  if (map.error) return <ApiError error={map.error as Error} />;
  if (!map.data) return <p className="text-muted-foreground">Loading map…</p>;
  const node = map.data.nodes.find((n) => n.id === selected) ?? null;
  const unlocks = node
    ? map.data.edges.filter((e) => e.source === node.id).map((e) => e.target)
    : [];
  const titleOf = (id: string) =>
    map.data!.nodes.find((n) => n.id === id)?.title ?? id;

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
      <KnowledgeMapView
        data={map.data}
        selected={selected}
        onSelect={(n) => onSelect(n.id)}
      />
      <aside className="rounded-2xl border border-border p-5">
        {!node ? (
          <p className="text-sm text-muted-foreground">
            Click a lesson on the map. Arrows point from a lesson to the lessons
            it unlocks. Locked lessons open after their prerequisites are done.
          </p>
        ) : (
          <div className="space-y-4">
            <StatusBadge status={node.status} />
            <h2 className="font-display text-xl font-bold">{node.title}</h2>
            <p className="text-sm text-muted-foreground">{node.summary}</p>
            {node.prerequisites.length > 0 && (
              <div className="text-sm">
                <p className="mb-1 font-medium">Needs first</p>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {node.prerequisites.map((p) => (
                    <li key={p}>{titleOf(p)}</li>
                  ))}
                </ul>
              </div>
            )}
            {unlocks.length > 0 && (
              <div className="text-sm">
                <p className="mb-1 font-medium">Unlocks</p>
                <ul className="list-disc pl-5 text-muted-foreground">
                  {unlocks.map((u) => (
                    <li key={u}>{titleOf(u)}</li>
                  ))}
                </ul>
              </div>
            )}
            <Button className="w-full" onClick={() => onOpen(node.id)}>
              {node.status === "locked" ? "Preview lesson" : "Open lesson"}
            </Button>
          </div>
        )}
      </aside>
    </div>
  );
}

function ApiError({ error }: { error: Error }) {
  return (
    <div className="rounded-2xl border border-destructive/50 bg-destructive/10 p-5 text-sm">
      <p className="font-semibold">The Learn backend is not reachable.</p>
      <p className="mt-1 text-muted-foreground">{error.message}</p>
      <p className="mt-3 text-muted-foreground">
        Start it from <code className="rounded bg-card px-1">backend/</code>{" "}
        with{" "}
        <code className="rounded bg-card px-1">
          python -m uvicorn app.main:app --port 8010
        </code>
        .
      </p>
    </div>
  );
}
