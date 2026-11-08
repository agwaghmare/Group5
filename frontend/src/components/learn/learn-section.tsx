import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  BookOpen,
  Clock,
  Download,
  Lock,
  Map as MapIcon,
  MessageCircleQuestion,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { CheckUnderstanding } from "@/components/learn/check-understanding";
import { ExplainThis } from "@/components/learn/explain-this";
import { ExplanationCard } from "@/components/learn/explanation-card";
import { KnowledgeMapView } from "@/components/learn/knowledge-map";
import { LessonAsk } from "@/components/learn/lesson-ask";
import {
  learnApi,
  learnUserId,
  type KnowledgeMap,
  type LessonSummary,
  type MapNode,
} from "@/lib/learn-api";

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
              {rows.map((l) => {
                const locked = l.status === "locked";
                return (
                  <button
                    key={l.id}
                    type="button"
                    disabled={locked}
                    aria-disabled={locked}
                    onClick={() => {
                      if (!locked) onOpen(l.id);
                    }}
                    className={`flex flex-col items-start gap-2 rounded-2xl border p-4 text-left transition-colors ${
                      locked
                        ? "cursor-not-allowed border-border opacity-70"
                        : "hover:bg-accent"
                    } ${l.id === recommended ? "border-primary" : "border-border"}`}
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
                );
              })}
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

  if (lesson.error) {
    const message = (lesson.error as Error).message;
    if (message.includes("403") || message.toLowerCase().includes("locked")) {
      return <LockedLesson onBack={onBack} />;
    }
    return <ApiError error={lesson.error as Error} />;
  }
  if (!lesson.data)
    return <p className="text-muted-foreground">Loading lesson…</p>;
  const l = lesson.data;
  if (l.status === "locked") return <LockedLesson onBack={onBack} />;
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
                  disabled={all.data?.lessons.find((row) => row.id === p)?.status === "locked"}
                  onClick={() => {
                    const row = all.data?.lessons.find((item) => item.id === p);
                    if (row?.status !== "locked") onOpenLesson(p);
                  }}
                >
                  {titleOf(p)}
                </Button>
              </span>
            ))}
          </p>
        )}
      </div>

      <LessonAsk
        key={`${l.id}-ask`}
        lessonId={l.id}
        lessonTitle={l.title}
        onOpenLesson={(id) => {
          const row = all.data?.lessons.find((item) => item.id === id);
          if (row?.status !== "locked") onOpenLesson(id);
        }}
      />

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

type MapLevel = "simple" | "learner" | "detailed";

type BuiltMap = {
  question: string;
  topicId: string | null;
  depth: number;
  level: MapLevel;
  reading: boolean;
  videos: boolean;
};

const MAP_SNAPSHOT_KEY = "finpilot.learn.map";
const STOP_WORDS = new Set([
  "how",
  "does",
  "what",
  "and",
  "the",
  "for",
  "with",
  "your",
  "this",
  "that",
  "are",
  "from",
  "into",
  "about",
  "connect",
  "connects",
  "connection",
]);

function questionTokens(question: string): string[] {
  return question
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((token) => token.length > 2 && !STOP_WORDS.has(token));
}

function focusMap(data: KnowledgeMap, built: BuiltMap): KnowledgeMap {
  const tokens = questionTokens(built.question);
  const topicName = (id: string) =>
    data.topics.find((topic) => topic.id === id)?.title ?? id;
  const matches = (node: MapNode) => {
    if (built.topicId && node.topic_id !== built.topicId) return false;
    if (tokens.length === 0) return true;
    const hay = `${node.title} ${node.summary} ${topicName(node.topic_id)}`.toLowerCase();
    return tokens.some((token) => hay.includes(token));
  };
  let seeds = data.nodes.filter(matches);
  if (seeds.length === 0) seeds = data.nodes;
  const neighbors = new Map<string, string[]>();
  for (const edge of data.edges) {
    neighbors.set(edge.source, [...(neighbors.get(edge.source) ?? []), edge.target]);
    neighbors.set(edge.target, [...(neighbors.get(edge.target) ?? []), edge.source]);
  }
  const keep = new Set(seeds.map((node) => node.id));
  let frontier = [...keep];
  for (let hop = 0; hop < built.depth; hop += 1) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const neighbor of neighbors.get(id) ?? []) {
        if (!keep.has(neighbor)) {
          keep.add(neighbor);
          next.push(neighbor);
        }
      }
    }
    frontier = next;
  }
  const nodes = data.nodes.filter((node) => keep.has(node.id));
  const topics = data.topics.filter((topic) =>
    nodes.some((node) => node.topic_id === topic.id),
  );
  const column = new Map(topics.map((topic, index) => [topic.id, index]));
  const rowCount = new Map<string, number>();
  const placed = nodes.map((node) => {
    const y = rowCount.get(node.topic_id) ?? 0;
    rowCount.set(node.topic_id, y + 1);
    return { ...node, x: column.get(node.topic_id) ?? 0, y };
  });
  return {
    ...data,
    topics,
    nodes: placed,
    edges: data.edges.filter(
      (edge) => keep.has(edge.source) && keep.has(edge.target),
    ),
  };
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
  const progress = useQuery({
    queryKey: ["learn", "progress", userId],
    queryFn: () => learnApi.progress(userId),
  });
  const [question, setQuestion] = useState(
    "How do credit, cash flow, and monthly bills connect?",
  );
  const [topicId, setTopicId] = useState<string | null>(null);
  const [depth, setDepth] = useState(2);
  const [level, setLevel] = useState<MapLevel>("simple");
  const [reading, setReading] = useState(true);
  const [videos, setVideos] = useState(true);
  const [built, setBuilt] = useState<BuiltMap | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const graph = useMemo(
    () => (map.data && built ? focusMap(map.data, built) : map.data ?? null),
    [map.data, built],
  );

  if (map.error) return <ApiError error={map.error as Error} />;
  if (!map.data || !graph) return <p className="text-muted-foreground">Loading map…</p>;

  const node = graph.nodes.find((item) => item.id === selected) ?? null;
  const titleOf = (id: string) =>
    map.data.nodes.find((item) => item.id === id)?.title ?? id;
  const build = () => {
    const tokens = questionTokens(question);
    const hit = map.data.nodes.some((item) => {
      if (topicId && item.topic_id !== topicId) return false;
      if (tokens.length === 0) return true;
      const topic = map.data.topics.find((row) => row.id === item.topic_id)?.title ?? "";
      const hay = `${item.title} ${item.summary} ${topic}`.toLowerCase();
      return tokens.some((token) => hay.includes(token));
    });
    setNote(
      hit
        ? null
        : "Nothing matched that question, so the map shows every lesson you can reach.",
    );
    setBuilt({ question, topicId, depth, level, reading, videos });
  };
  const exportMap = () => {
    const snapshot = {
      exported_at: new Date().toISOString(),
      question: built?.question ?? question,
      connection_depth: built?.depth ?? depth,
      explanation_level: built?.level ?? level,
      find_reading: built?.reading ?? reading,
      find_videos: built?.videos ?? videos,
      completed_lessons: progress.data?.completed_lessons ?? [],
      topics: graph.topics,
      nodes: graph.nodes,
      edges: graph.edges,
    };
    const file = new Blob([JSON.stringify(snapshot, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "finpilot-knowledge-map.json";
    link.click();
    URL.revokeObjectURL(url);
    window.localStorage.setItem(MAP_SNAPSHOT_KEY, JSON.stringify(snapshot));
    setNote("Map saved in this browser and downloaded as finpilot-knowledge-map.json.");
  };
  const searchFor = (title: string, site: "reading" | "videos") => {
    const q = encodeURIComponent(`${title} personal finance explained`);
    const href =
      site === "videos"
        ? `https://www.youtube.com/results?search_query=${q}`
        : `https://www.google.com/search?q=${q}`;
    window.open(href, "_blank", "noopener,noreferrer");
  };

  return (
    <div className="grid gap-6 lg:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="space-y-5 rounded-2xl border border-border bg-card/40 p-5">
        <div>
          <p className="font-display text-xs font-bold uppercase tracking-[0.3em] text-primary">
            Start with a question
          </p>
          <label className="mt-3 mb-1 block text-xs text-muted-foreground" htmlFor="map-question">
            What would you like to understand?
          </label>
          <Textarea
            id="map-question"
            value={question}
            onChange={(ev) => setQuestion(ev.target.value)}
            rows={3}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {map.data.topics.map((topic) => (
            <button
              key={topic.id}
              type="button"
              onClick={() => {
                setTopicId(topic.id);
                setQuestion(`How does ${topic.title.toLowerCase()} connect?`);
              }}
              className={`rounded-full border px-3 py-1 text-xs ${
                topicId === topic.id
                  ? "border-primary bg-primary text-primary-foreground"
                  : "border-border text-foreground hover:bg-accent"
              }`}
            >
              {topic.title}
            </button>
          ))}
        </div>
        <details className="rounded-2xl border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">
            Customize depth and sources
          </summary>
          <div className="mt-4 space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between text-xs text-muted-foreground">
                <span>Connection depth</span>
                <span>{depth}</span>
              </div>
              <Slider
                min={1}
                max={3}
                step={1}
                value={[depth]}
                onValueChange={(value) => setDepth(value[0] ?? 1)}
                aria-label="Connection depth"
              />
            </div>
            <label className="block text-xs text-muted-foreground" htmlFor="map-level">
              Explanation level
              <select
                id="map-level"
                value={level}
                onChange={(ev) => setLevel(ev.target.value as MapLevel)}
                className="mt-1 w-full rounded-xl border border-border bg-background px-3 py-2 text-sm text-foreground"
              >
                <option value="simple">Start simple</option>
                <option value="learner">Show the mechanism</option>
                <option value="detailed">Show the formula</option>
              </select>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={reading}
                onCheckedChange={(value) => setReading(value === true)}
              />
              Find a reading
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={videos}
                onCheckedChange={(value) => setVideos(value === true)}
              />
              Find videos
            </label>
          </div>
        </details>
        <Button className="w-full" onClick={build}>
          Build my knowledge map
        </Button>
        <Button className="w-full" variant="outline" onClick={exportMap}>
          <Download aria-hidden="true" /> Export map
        </Button>
      </aside>

      <section className="min-w-0 space-y-4">
        <div>
          <h2 className="font-display text-2xl font-extrabold md:text-3xl">
            {built?.question || "Follow your curiosity."}
          </h2>
          <p className="text-sm text-muted-foreground">See what connects.</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Badge variant={(built?.reading ?? reading) ? "default" : "secondary"}>
              Reading {(built?.reading ?? reading) ? "on" : "off"}
            </Badge>
            <Badge variant={(built?.videos ?? videos) ? "default" : "secondary"}>
              Videos {(built?.videos ?? videos) ? "on" : "off"}
            </Badge>
            <Badge variant="outline">{(built?.level ?? level).replace("learner", "mechanism")}</Badge>
          </div>
        </div>
        {note && <p className="text-sm text-muted-foreground">{note}</p>}
        <KnowledgeMapView
          data={graph}
          selected={selected}
          onSelect={(item) => onSelect(item.id)}
        />
        <div className="flex flex-wrap gap-2">
          {graph.nodes.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => onSelect(item.id)}
              className={`rounded-md border px-2.5 py-1 text-xs ${
                item.id === selected
                  ? "border-[#fb7185] text-foreground"
                  : "border-border text-muted-foreground"
              }`}
            >
              {item.title}
            </button>
          ))}
        </div>
        <ConceptDetail
          node={node}
          level={built?.level ?? level}
          reading={built?.reading ?? reading}
          videos={built?.videos ?? videos}
          userId={userId}
          titleOf={titleOf}
          onOpen={onOpen}
          onSearch={searchFor}
        />
      </section>
    </div>
  );
}

function ConceptDetail({
  node,
  level,
  reading,
  videos,
  userId,
  titleOf,
  onOpen,
  onSearch,
}: {
  node: MapNode | null;
  level: MapLevel;
  reading: boolean;
  videos: boolean;
  userId: string;
  titleOf: (id: string) => string;
  onOpen: (id: string) => void;
  onSearch: (title: string, site: "reading" | "videos") => void;
}) {
  const locked = node?.status === "locked";
  const lesson = useQuery({
    queryKey: ["learn", "lesson", node?.id, userId],
    queryFn: () => learnApi.lesson(node!.id, userId),
    enabled: Boolean(node) && !locked,
  });
  const deeper = useQuery({
    queryKey: ["learn", "deeper", node?.id, userId],
    queryFn: () => learnApi.goDeeper(node!.id, userId),
    enabled: Boolean(node) && !locked && level === "detailed",
  });
  if (!node) {
    return (
      <p className="text-sm text-muted-foreground">
        Build the map, then select a concept. Locked lessons stay closed until
        their prerequisites are done.
      </p>
    );
  }
  const explanation = lesson.data?.explanation;
  const body =
    level === "detailed"
      ? (deeper.data?.detail ?? explanation?.one_sentence ?? node.summary)
      : level === "learner"
        ? (explanation?.analogy ?? node.summary)
        : (explanation?.one_sentence ?? node.summary);
  return (
    <div className="rounded-2xl border border-border p-5">
      <StatusBadge status={node.status} />
      <h3 className="mt-3 font-display text-xl font-bold">{node.title}</h3>
      <p className="mt-2 text-sm text-muted-foreground">{body}</p>
      {node.prerequisites.length > 0 && (
        <p className="mt-3 text-sm text-muted-foreground">
          Needs first: {node.prerequisites.map(titleOf).join(", ")}
        </p>
      )}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button disabled={locked} onClick={() => onOpen(node.id)}>
          {locked ? "Locked" : "Open lesson"}
        </Button>
        {reading && (
          <Button variant="outline" onClick={() => onSearch(node.title, "reading")}>
            Find a reading
          </Button>
        )}
        {videos && (
          <Button variant="outline" onClick={() => onSearch(node.title, "videos")}>
            Find a video
          </Button>
        )}
      </div>
    </div>
  );
}

function LockedLesson({ onBack }: { onBack: () => void }) {
  return (
    <div className="mx-auto max-w-xl rounded-2xl border border-border p-6">
      <Button variant="ghost" className="-ml-3 mb-3" onClick={onBack}>
        <ArrowLeft aria-hidden="true" /> All lessons
      </Button>
      <div className="mb-3 flex items-center gap-2 font-display text-xl font-bold">
        <Lock aria-hidden="true" /> This lesson is locked
      </div>
      <p className="text-sm text-muted-foreground">
        Finish the lessons it builds on. You can open it after those are done.
      </p>
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
