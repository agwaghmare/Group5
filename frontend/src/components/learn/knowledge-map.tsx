import { useEffect, useMemo, useRef, useState } from "react";
import type {
  KnowledgeMap as KnowledgeMapData,
  MapEdge,
  MapNode,
} from "@/lib/learn-api";

const BOX_W = 168;
const BOX_H = 64;
const GAP_X = 28;
const GAP_Y = 56;
const PAD = 36;

type Box = { x: number; y: number };
type Branch = { id: string; children: Branch[] };

function treeEdges(nodes: MapNode[], edges: MapEdge[]): MapEdge[] {
  const ids = new Set(nodes.map((node) => node.id));
  const seen = new Set<string>();
  const kept: MapEdge[] = [];
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target) || seen.has(edge.target))
      continue;
    seen.add(edge.target);
    kept.push(edge);
  }
  return kept;
}

function forest(nodes: MapNode[], edges: MapEdge[]): Branch[] {
  const kids = new Map<string, string[]>();
  const child = new Set<string>();
  for (const node of nodes) kids.set(node.id, []);
  for (const edge of treeEdges(nodes, edges)) {
    kids.get(edge.source)!.push(edge.target);
    child.add(edge.target);
  }
  const grow = (id: string, seen: Set<string>): Branch => {
    if (seen.has(id)) return { id, children: [] };
    const next = new Set(seen);
    next.add(id);
    return {
      id,
      children: (kids.get(id) ?? []).map((kid) => grow(kid, next)),
    };
  };
  return nodes
    .filter((node) => !child.has(node.id))
    .map((node) => grow(node.id, new Set()));
}

function labelLines(title: string) {
  const words = title.split(/\s+/).filter(Boolean);
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const next = current ? `${current} ${word}` : word;
    if (current && next.length > 22) {
      lines.push(current);
      current = word;
    } else {
      current = next;
    }
  }
  if (current) lines.push(current);
  return lines.slice(0, 3);
}

function layoutTree(nodes: MapNode[], edges: MapEdge[]) {
  const roots = forest(nodes, edges);
  const widthOf = (branch: Branch): number => {
    if (branch.children.length === 0) return BOX_W;
    const inner = branch.children.reduce(
      (sum, child) => sum + widthOf(child),
      0,
    );
    return inner + GAP_X * (branch.children.length - 1);
  };
  const pos = new Map<string, Box>();
  const place = (branch: Branch, left: number, depth: number) => {
    const width = widthOf(branch);
    const y = PAD + depth * (BOX_H + GAP_Y);
    if (branch.children.length === 0) {
      pos.set(branch.id, { x: left, y });
      return;
    }
    let cursor = left;
    for (const child of branch.children) {
      place(child, cursor, depth + 1);
      cursor += widthOf(child) + GAP_X;
    }
    const first = pos.get(branch.children[0]!.id)!;
    const last = pos.get(branch.children[branch.children.length - 1]!.id)!;
    pos.set(branch.id, {
      x: (first.x + last.x + BOX_W) / 2 - BOX_W / 2,
      y,
    });
    void width;
  };
  let cursor = PAD;
  let maxDepth = 0;
  const walk = (branch: Branch, depth: number) => {
    maxDepth = Math.max(maxDepth, depth);
    branch.children.forEach((child) => walk(child, depth + 1));
  };
  roots.forEach((root) => walk(root, 0));
  for (const root of roots) {
    place(root, cursor, 0);
    cursor += widthOf(root) + GAP_X * 2;
  }
  let maxX = PAD + BOX_W;
  let maxY = PAD + BOX_H;
  for (const box of pos.values()) {
    maxX = Math.max(maxX, box.x + BOX_W);
    maxY = Math.max(maxY, box.y + BOX_H);
  }
  return {
    pos,
    edges: treeEdges(nodes, edges),
    worldW: maxX + PAD,
    worldH: maxY + PAD,
    depth: maxDepth,
  };
}

/** Top-down tree. Each concept has one parent, and the link is a right-angle elbow in the gap. */
export function KnowledgeMapView({
  data,
  selected,
  onSelect,
}: {
  data: KnowledgeMapData;
  selected?: string | null;
  onSelect: (node: MapNode) => void;
}) {
  const layout = useMemo(
    () => layoutTree(data.nodes, data.edges),
    [data.nodes, data.edges],
  );
  const [query, setQuery] = useState("");
  const [camera, setCamera] = useState({ x: 0, y: 0, k: 1 });
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(
    null,
  );
  const frame = useRef<HTMLDivElement>(null);
  const cameraRef = useRef(camera);
  const worldRef = useRef({ w: layout.worldW, h: layout.worldH });
  cameraRef.current = camera;
  worldRef.current = { w: layout.worldW, h: layout.worldH };
  const needle = query.trim().toLowerCase();

  useEffect(() => {
    const node = frame.current;
    if (!node) return;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      const current = cameraRef.current;
      const world = worldRef.current;
      const next = Math.min(
        1.8,
        Math.max(0.55, current.k * (event.deltaY > 0 ? 0.92 : 1.08)),
      );
      const px = ((event.clientX - rect.left) / rect.width) * world.w;
      const py = ((event.clientY - rect.top) / rect.height) * world.h;
      setCamera({
        k: next,
        x: px - worldX(px, current, next),
        y: py - worldY(py, current, next),
      });
    };
    const worldX = (
      px: number,
      current: { x: number; k: number },
      next: number,
    ) => ((px - current.x) / current.k) * next;
    const worldY = (
      py: number,
      current: { y: number; k: number },
      next: number,
    ) => ((py - current.y) / current.k) * next;
    node.addEventListener("wheel", onWheel, { passive: false });
    return () => node.removeEventListener("wheel", onWheel);
  }, []);

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-[#101318]">
      <div className="border-b border-white/10 px-4 py-3">
        <label className="sr-only" htmlFor="find-concept">
          Find a concept
        </label>
        <input
          id="find-concept"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Find a concept"
          className="w-full bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
        />
      </div>
      <div
        ref={frame}
        className="relative h-[540px] cursor-grab touch-none active:cursor-grabbing"
        onPointerDown={(event) => {
          const target = event.target as Element | null;
          if (target?.closest?.("[data-node]")) return;
          drag.current = {
            x: event.clientX,
            y: event.clientY,
            cx: camera.x,
            cy: camera.y,
          };
          try {
            (event.currentTarget as HTMLDivElement).setPointerCapture(
              event.pointerId,
            );
          } catch {
            /* The pointer can end before capture is attached. */
          }
        }}
        onPointerMove={(event) => {
          const start = drag.current;
          const node = frame.current;
          if (!start || !node) return;
          const rect = node.getBoundingClientRect();
          if (rect.width < 1 || rect.height < 1) return;
          const dx = ((event.clientX - start.x) / rect.width) * layout.worldW;
          const dy = ((event.clientY - start.y) / rect.height) * layout.worldH;
          const x = start.cx + dx;
          const y = start.cy + dy;
          if (!Number.isFinite(x) || !Number.isFinite(y)) return;
          setCamera((current) => ({ ...current, x, y }));
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <svg
          viewBox={`0 0 ${layout.worldW} ${layout.worldH}`}
          preserveAspectRatio="xMidYMid meet"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Knowledge map arranged as a top-down tree"
        >
          <g
            transform={`translate(${camera.x} ${camera.y}) scale(${camera.k})`}
          >
            {layout.edges.map((edge) => {
              const from = layout.pos.get(edge.source);
              const to = layout.pos.get(edge.target);
              if (!from || !to) return null;
              const x1 = from.x + BOX_W / 2;
              const y1 = from.y + BOX_H;
              const x2 = to.x + BOX_W / 2;
              const y2 = to.y;
              const mid = y1 + (y2 - y1) / 2;
              const active =
                edge.source === selected || edge.target === selected;
              return (
                <path
                  key={`${edge.source}->${edge.target}`}
                  d={`M ${x1} ${y1} L ${x1} ${mid} L ${x2} ${mid} L ${x2} ${y2}`}
                  fill="none"
                  stroke={active ? "#d7deea" : "#6b7385"}
                  strokeWidth="1.25"
                />
              );
            })}
            {data.nodes.map((node) => {
              const box = layout.pos.get(node.id);
              if (!box) return null;
              const match =
                !needle || node.title.toLowerCase().includes(needle);
              const isSel = node.id === selected;
              return (
                <g
                  key={node.id}
                  data-node="true"
                  role="button"
                  tabIndex={0}
                  aria-label={`${node.title} (${node.status})`}
                  className="cursor-pointer"
                  opacity={match ? 1 : 0.28}
                  onClick={() => onSelect(node)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      onSelect(node);
                    }
                  }}
                >
                  <rect
                    x={box.x}
                    y={box.y}
                    width={BOX_W}
                    height={BOX_H}
                    rx="8"
                    fill="#1a2230"
                    stroke={isSel ? "#fb7185" : "#3d4658"}
                    strokeWidth={isSel ? 2.4 : 1.2}
                  />
                  <text
                    x={box.x + BOX_W / 2}
                    y={box.y + 22}
                    textAnchor="middle"
                    fill={node.status === "locked" ? "#9aa3b5" : "#f4f7fb"}
                    fontSize="12"
                  >
                    {labelLines(node.title).map((line, index) => (
                      <tspan
                        key={`${index}-${line}`}
                        x={box.x + BOX_W / 2}
                        dy={index === 0 ? 0 : 14}
                      >
                        {line}
                      </tspan>
                    ))}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <p className="border-t border-white/10 px-4 py-2 text-xs text-muted-foreground">
        Pan and zoom to explore. Select a concept on the graph or use the list
        below. {data.nodes.length} concepts
      </p>
    </div>
  );
}
