import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AssistantRail } from "@/components/employee/assistant-rail";
import { staffFetch } from "@/lib/staff-api";

vi.mock("@/lib/staff-api", () => ({ staffFetch: vi.fn() }));
beforeEach(() => {
  vi.mocked(staffFetch).mockReset();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Employee assistant chat", () => {
  it("keeps the Bessie identity even when the current feature explains a term", async () => {
    vi.mocked(staffFetch).mockResolvedValue({
      answer: "Hi, I'm Bessie. How can I help?",
      provider: "nvidia",
      status: "evidence_validated",
    });
    render(<AssistantRail featureId="learn.explain" hint="Your workspace" />);
    fireEvent.change(screen.getByLabelText("Ask Bessie"), {
      target: { value: "hi" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask Bessie" }));
    expect(
      await screen.findByText("Hi, I'm Bessie. How can I help?"),
    ).toBeInTheDocument();
    expect(staffFetch).toHaveBeenCalledWith(
      "/assistant",
      expect.objectContaining({
        body: expect.objectContaining({ agent: "bessie", question: "hi" }),
      }),
    );
    expect(screen.queryByText(/evidence_validated/)).toBeNull();
  });

  it("only chooses Wilbur when explicitly opened as Wilbur", async () => {
    vi.mocked(staffFetch).mockResolvedValue({ answer: "Hi, I'm Wilbur." });
    render(
      <AssistantRail
        featureId="learn.explain"
        agent="wilbur"
        hint="Explain this"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hi" }));
    expect(await screen.findByText("Hi, I'm Wilbur.")).toBeInTheDocument();
    expect(staffFetch).toHaveBeenCalledWith(
      "/assistant",
      expect.objectContaining({
        body: expect.objectContaining({ agent: "wilbur" }),
      }),
    );
  });

  it("times out visibly and prevents duplicate requests", async () => {
    vi.useFakeTimers();
    vi.mocked(staffFetch).mockImplementation(
      (_path, init) =>
        new Promise<never>((_, reject) => {
          init?.signal?.addEventListener("abort", () =>
            reject(new DOMException("Aborted", "AbortError")),
          );
        }),
    );
    render(<AssistantRail featureId="staff.access" hint="Your workspace" />);
    fireEvent.click(screen.getByRole("button", { name: "Hi" }));
    fireEvent.click(
      screen.getByRole("button", { name: "What can you help me with?" }),
    );
    expect(staffFetch).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(25_000);
    });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Bessie took too long. Please try again.",
    );
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Hi" })).not.toBeDisabled();
  });

  it("cancels the old request when its workspace is unmounted", () => {
    let signal: AbortSignal | undefined;
    vi.mocked(staffFetch).mockImplementation((_path, init) => {
      signal = init?.signal;
      return new Promise<never>(() => {});
    });
    const view = render(
      <AssistantRail featureId="staff.access" hint="Your workspace" />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Hi" }));
    view.unmount();
    expect(signal?.aborted).toBe(true);
  });
});
