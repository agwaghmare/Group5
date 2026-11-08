import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { KnowledgeMapView } from "@/components/learn/knowledge-map";
import type { MapNode } from "@/lib/learn-api";

function node(id: string, title: string): MapNode {
  return {
    id,
    topic_id: "credit",
    title,
    minutes: 4,
    summary: title,
    prerequisites: [],
    status: "available",
    x: 0,
    y: 0,
  };
}

describe("KnowledgeMapView", () => {
  it("pans the tree without throwing", () => {
    render(
      <KnowledgeMapView
        data={{
          view: "knowledge_map",
          topics: [{ id: "credit", title: "Credit" }],
          nodes: [
            node("apr", "Annual percentage rate"),
            node("use", "Credit utilization"),
          ],
          edges: [{ source: "apr", target: "use", kind: "prereq" }],
        }}
        onSelect={() => undefined}
      />,
    );
    const frame = screen.getByRole("img", {
      name: "Knowledge map arranged as a top-down tree",
    }).parentElement!;
    frame.getBoundingClientRect = () =>
      ({
        width: 400,
        height: 540,
        left: 0,
        top: 0,
        right: 400,
        bottom: 540,
        x: 0,
        y: 0,
        toJSON() {
          return {};
        },
      }) as DOMRect;
    fireEvent.pointerDown(frame, { clientX: 40, clientY: 40, pointerId: 1 });
    fireEvent.pointerMove(frame, { clientX: 140, clientY: 120, pointerId: 1 });
    fireEvent.pointerUp(frame, { pointerId: 1 });
    expect(
      screen.getByRole("button", {
        name: "Annual percentage rate (available)",
      }),
    ).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Credit utilization (available)" }),
    ).toBeTruthy();
  });
});
