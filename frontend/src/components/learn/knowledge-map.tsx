import { useMemo } from "react";
import { Check, Lock } from "lucide-react";
import type {
  KnowledgeMap as KnowledgeMapData,
  MapNode,
} from "@/lib/learn-api";

const COL_W = 196;
const ROW_H = 92;
const NODE_W = 164;
const NODE_H = 60;
const PAD = 24;

/**
 * Prerequisite graph. Columns are topics (left → right), rows are lesson order within a topic.
 * Edges are drawn as curves from a prerequisite to the lesson it unlocks.
 */
export function KnowledgeMapView({
  data,
  selected,
  onSelect,
}: {
  data: KnowledgeMapData;
  selected?: string | null;
  onSelect: (node: MapNode) => void;
}) {
  const pos = useMemo(() => {
    const map = new Map<string, { x: number; y: number }>();
    for (const n of data.nodes) {
      map.set(n.id, { x: PAD + n.x * COL_W, y: PAD + 36 + n.y * ROW_H });
    }
    return map;
  }, [data.nodes]);

  const cols = data.topics.length;
  const rows = Math.max(1, ...data.nodes.map((n) => n.y + 1));
  const width = PAD * 2 + cols * COL_W;
  const height = PAD * 2 + 36 + rows * ROW_H;

  return (
    <div className="overflow-auto rounded-2xl border border-border bg-card/40">
      <svg
        width={width}
        height={height}
        role="img"
        aria-label="Knowledge map of lessons and prerequisites"
        className="block"
      >
        {data.topics.map((t, i) => (
          <text
            key={t.id}
            x={PAD + i * COL_W + NODE_W / 2}
            y={PAD + 12}
            textAnchor="middle"
            className="fill-muted-foreground font-display text-[10px] font-bold uppercase tracking-[0.2em]"
          >
            {t.title}
          </text>
        ))}
        {data.edges.map((e) => {
          const a = pos.get(e.source);
          const b = pos.get(e.target);
          if (!a || !b) return null;
          const x1 = a.x + NODE_W / 2;
          const y1 = a.y + NODE_H;
          const x2 = b.x + NODE_W / 2;
          const y2 = b.y;
          const sameCol = Math.abs(x1 - x2) < 1;
          const d = sameCol
            ? `M ${x1} ${y1} L ${x2} ${y2}`
            : `M ${x1} ${y1} C ${x1} ${y1 + 40}, ${x2} ${y2 - 40}, ${x2} ${y2}`;
          const active = e.target === selected || e.source === selected;
          return (
            <path
              key={`${e.source}->${e.target}`}
              d={d}
              fill="none"
              className={active ? "stroke-primary" : "stroke-border"}
              strokeWidth={active ? 2 : 1.25}
              markerEnd="url(#arrow)"
            />
          );
        })}
        <defs>
          <marker
            id="arrow"
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" className="fill-border" />
          </marker>
        </defs>
        {data.nodes.map((n) => {
          const p = pos.get(n.id)!;
          const isSel = n.id === selected;
          const fill =
            n.status === "completed"
              ? "fill-primary"
              : n.status === "locked"
                ? "fill-muted"
                : "fill-card";
          const stroke = isSel
            ? "stroke-primary"
            : n.status === "locked"
              ? "stroke-border"
              : "stroke-primary/60";
          const text =
            n.status === "completed"
              ? "fill-primary-foreground"
              : n.status === "locked"
                ? "fill-muted-foreground"
                : "fill-foreground";
          return (
            <g
              key={n.id}
              role="button"
              tabIndex={0}
              aria-label={`${n.title} (${n.status})`}
              className="cursor-pointer"
              onClick={() => onSelect(n)}
              onKeyDown={(ev) => {
                if (ev.key === "Enter" || ev.key === " ") {
                  ev.preventDefault();
                  onSelect(n);
                }
              }}
            >
              <rect
                x={p.x}
                y={p.y}
                width={NODE_W}
                height={NODE_H}
                rx={14}
                className={`${fill} ${stroke}`}
                strokeWidth={isSel ? 2.5 : 1.5}
              />
              <foreignObject
                x={p.x + 10}
                y={p.y + 6}
                width={NODE_W - 20}
                height={NODE_H - 12}
              >
                <div className="flex h-full items-center gap-2">
                  {n.status === "completed" ? (
                    <Check
                      className="size-3.5 shrink-0 text-primary-foreground"
                      aria-hidden="true"
                    />
                  ) : n.status === "locked" ? (
                    <Lock
                      className="size-3.5 shrink-0 text-muted-foreground"
                      aria-hidden="true"
                    />
                  ) : null}
                  <span
                    className={`line-clamp-2 text-[11px] leading-tight ${text.replace("fill-", "text-")}`}
                  >
                    {n.title}
                  </span>
                </div>
              </foreignObject>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
