import { describe, expect, it } from "vitest";
import { reachesCenter, shouldOpenFifthPage } from "@/lib/wheel-navigation";

describe("Wheel destination", () => {
  it("recognizes the middle as the drop target", () => {
    expect(reachesCenter(600, 400, 1200, 800)).toBe(true);
  });
  it("does not open page five at the wheel's bottom-left starting position", () => {
    expect(reachesCenter(100, 700, 1200, 800)).toBe(false);
  });
  it("does not open page five while dragging through the middle", () => {
    expect(shouldOpenFifthPage("move", true, 600, 400, 1200, 800)).toBe(false);
  });
  it("opens page five after a dragged wheel is dropped in the middle", () => {
    expect(shouldOpenFifthPage("drop", true, 600, 400, 1200, 800)).toBe(true);
  });
  it("does not open page five for a drop outside the middle", () => {
    expect(shouldOpenFifthPage("drop", true, 100, 700, 1200, 800)).toBe(false);
  });
  it("does not open page five for a click without dragging", () => {
    expect(shouldOpenFifthPage("drop", false, 600, 400, 1200, 800)).toBe(false);
  });
  it("does not open page five when the drag is cancelled", () => {
    expect(shouldOpenFifthPage("cancel", true, 600, 400, 1200, 800)).toBe(false);
  });
});