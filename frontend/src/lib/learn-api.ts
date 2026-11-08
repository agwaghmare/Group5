// Typed client for the Learn backend (backend/app/routers/learn.py).
// In dev, Vite proxies /api/* to FastAPI; in production set VITE_LEARN_API_URL.
import { readCustomerSession } from "@/lib/customer-session";

const BASE =
  (import.meta.env["VITE_LEARN_API_URL"] as string | undefined) ?? "/api";

export type LessonStatus = "completed" | "available" | "locked";

export interface Topic {
  id: string;
  title: string;
  summary: string;
  lesson_count?: number;
}

export interface LessonSummary {
  id: string;
  topic_id: string;
  title: string;
  minutes: number;
  summary: string;
  prerequisites: string[];
  status: LessonStatus;
}

export interface QuizQuestion {
  id: string;
  prompt: string;
  choices: string[];
}

export interface WorkedExample {
  label: "your numbers" | "toy numbers";
  disclaimer: string;
  title: string;
  steps: string[];
  result: string;
}

export interface GoDeeper {
  control: "go_deeper";
  expanded: boolean;
  path: string;
  symbols?: string[];
  detail?: string;
}

export interface Explanation {
  sequence: string[];
  one_sentence: string;
  analogy: string;
  worked_example: WorkedExample;
  what_this_means_for_you: string;
  safe_next_step: string;
  go_deeper: GoDeeper;
  check_my_understanding?: {
    control: "check_my_understanding";
    prompt?: string;
    submit_path?: string;
    questions?: QuizQuestion[];
    lesson_id?: string;
    path?: string;
  };
}

export interface LessonDetail extends LessonSummary {
  view: "lessons";
  check_my_understanding_result: {
    correct: number;
    total: number;
    score: number;
  } | null;
  explanation: Explanation;
}

export interface MapNode extends LessonSummary {
  x: number;
  y: number;
}

export interface MapEdge {
  source: string;
  target: string;
  kind: string;
}

export interface KnowledgeMap {
  view: "knowledge_map";
  topics: Topic[];
  nodes: MapNode[];
  edges: MapEdge[];
}

export interface GradedQuestion {
  id: string;
  chosen: number | null;
  answer_index: number;
  correct: boolean;
  explanation: { simple: string; learner: string; detailed: string };
}

export interface GradeResult {
  lesson_id?: string;
  scenario_id?: string;
  correct: number;
  total: number;
  score: number;
  questions: GradedQuestion[];
  progress: Progress;
  reward?: (LearnRewardBalance & { awarded: number; already_earned: boolean }) | null;
}

export interface LearnRewardBalance {
  currency: string;
  balance: number;
  per_lesson: number;
  pass_score: number;
  description: string;
  earned_lessons: { lesson_id: string; amount: number; earned_at: string }[];
}

export interface Progress {
  user_id: string;
  preferred_level: string;
  current_lesson_id: string | null;
  completed_lessons: string[];
  quiz_results: Record<
    string,
    { correct: number; total: number; score: number }
  >;
  scenario_results: Record<
    string,
    { correct: number; total: number; score: number }
  >;
  viewed_questions: string[];
  recommended_lesson_id: string | null;
}

export interface Prompt {
  id: string;
  label: string;
  topic_id: string;
  lesson_id: string;
  highlighted: boolean;
}

export interface ExplainResult {
  matched: boolean;
  question_id?: string;
  label?: string;
  lesson_id?: string;
  lesson_title?: string;
  explanation: Explanation;
  your_numbers?: {
    contract: Record<string, unknown>;
    tracker: Record<string, unknown>;
  };
  notes: string[];
  prompts?: Prompt[];
  wilbur?: {
    agent: "Wilbur";
    answer: string;
    reasons: string[];
    limitations: string[];
  };
}

export interface Scenario {
  id: string;
  topic_id: string;
  title: string;
  lesson_id: string;
  situation: string;
  check_my_understanding?: { questions: QuizQuestion[] };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const session = readCustomerSession();
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (session?.token) headers.set("Authorization", `Bearer ${session.token}`);
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      // keep statusText
    }
    throw new Error(`Learn API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

const q = (
  params: Record<string, string | number | boolean | undefined | null>,
) => {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== "")
      search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
};

export const learnApi = {
  rewards: () => request<LearnRewardBalance>("/learn/rewards"),
  topics: () => request<{ topics: Topic[] }>("/learn/topics"),
  lessons: (userId: string, topicId?: string) =>
    request<{ lessons: LessonSummary[] }>(
      `/learn/lessons${q({ user_id: userId, topic_id: topicId })}`,
    ),
  lesson: (lessonId: string, userId: string, goDeeper = false) =>
    request<LessonDetail>(
      `/learn/lessons/${lessonId}${q({ user_id: userId, go_deeper: goDeeper || undefined })}`,
    ),
  goDeeper: (lessonId: string, userId: string) =>
    request<GoDeeper>(
      `/learn/lessons/${lessonId}/go-deeper${q({ user_id: userId })}`,
    ),
  checkUnderstanding: (
    lessonId: string,
    userId: string,
    answers: Record<string, number>,
  ) =>
    request<GradeResult>(`/learn/lessons/${lessonId}/check-my-understanding`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, answers }),
    }),
  map: (userId: string) =>
    request<KnowledgeMap>(`/learn/map${q({ user_id: userId })}`),
  progress: (userId: string) => request<Progress>(`/learn/progress/${userId}`),
  scenarios: () => request<{ scenarios: Scenario[] }>("/learn/scenarios"),
  scenario: (scenarioId: string) =>
    request<Scenario>(`/learn/scenarios/${scenarioId}`),
  gradeScenario: (
    scenarioId: string,
    userId: string,
    answers: Record<string, number>,
  ) =>
    request<GradeResult>(`/learn/scenarios/${scenarioId}/grade`, {
      method: "POST",
      body: JSON.stringify({ user_id: userId, answers }),
    }),
  prompts: (customerId?: string, trackerUserId?: number) =>
    request<{ prompts: Prompt[]; notes: string[] }>(
      `/learn/context/prompts${q({ customer_id: customerId, tracker_user_id: trackerUserId })}`,
    ),
  explain: (body: {
    question_id?: string | undefined;
    question?: string | undefined;
    customer_id?: string | undefined;
    tracker_user_id?: number | undefined;
    user_id?: string | undefined;
    lesson_id?: string | undefined;
    go_deeper?: boolean | undefined;
  }) =>
    request<ExplainResult>(readCustomerSession()?.token && !body.go_deeper ? "/learn/wilbur" : "/learn/context/explain", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

const USER_KEY = "finpilot.learn.user";

/** A stable local learner id so progress survives reloads without a sign-in. */
export function learnUserId(): string {
  const session = readCustomerSession();
  if (session?.token) return `account:${session.email}`;
  if (typeof window === "undefined") return "local";
  let id = window.localStorage.getItem(USER_KEY);
  if (!id) {
    id = `learner-${Math.random().toString(36).slice(2, 10)}`;
    window.localStorage.setItem(USER_KEY, id);
  }
  return id;
}
