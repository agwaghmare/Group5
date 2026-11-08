import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AmeliaRail } from "@/components/finance/finance-section";
import { askAmelia } from "@/lib/finance-api";

vi.mock("@/lib/finance-api", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/lib/finance-api")>(),
  askAmelia: vi.fn(),
}));

const answer = {
  answer: "Your recorded debt needs a review.", reasons: ["Review the recorded interest rate."],
  limitations: ["Scenario slider changes are not included."], provider: "nvidia",
  status: "evidence_validated", agent: "Amelia",
};

describe("Amelia prompt selection", () => {
  beforeEach(() => vi.mocked(askAmelia).mockReset());
  afterEach(cleanup);

  it("fills Picture for the active tab and waits for submission", async () => {
    vi.mocked(askAmelia).mockResolvedValue(answer);
    render(<AmeliaRail featureId="fin.debt" hint="Recorded tracker" />);
    fireEvent.click(screen.getByRole("button", { name: "Picture" }));
    expect((screen.getByRole("textbox", { name: "Ask Amelia" }) as HTMLTextAreaElement).value).toContain("current picture of the Loans & Health tab");
    expect(askAmelia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ask Amelia" }));
    await waitFor(() => expect(askAmelia).toHaveBeenCalledWith("fin.debt", expect.stringContaining("Loans & Health")));
    expect(await screen.findByText(/Review the recorded interest rate/)).toBeInTheDocument();
    expect(screen.queryByText(/evidence_validated/)).not.toBeInTheDocument();
  });

  it("fills the shock action-plan question and uses shock evidence", async () => {
    vi.mocked(askAmelia).mockResolvedValue(answer);
    render(<AmeliaRail featureId="fin.profile" hint="Recorded tracker" />);
    fireEvent.click(screen.getByRole("button", { name: "Shock" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("If I get a financial shock, what is my plan of action?");
    expect(askAmelia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ask Amelia" }));
    await waitFor(() => expect(askAmelia).toHaveBeenCalledWith("fin.immune", expect.any(String)));
  });

  it("uses the appropriate evidence for suggestion buttons", async () => {
    vi.mocked(askAmelia).mockResolvedValue(answer);
    render(<AmeliaRail featureId="fin.debt" hint="Recorded tracker" />);
    fireEvent.click(screen.getByRole("button", { name: "Where is money leaking?" }));
    expect(askAmelia).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Ask Amelia" }));
    await waitFor(() => expect(askAmelia).toHaveBeenCalledWith("fin.moneyleaks", expect.stringContaining("Loans & Health")));
  });

  it("ignores old replies when the active tab changes", async () => {
    let resolve!: (value: typeof answer) => void;
    vi.mocked(askAmelia).mockReturnValue(new Promise((done) => { resolve = done; }));
    const { rerender } = render(<AmeliaRail featureId="fin.debt" hint="Recorded tracker" />);
    fireEvent.click(screen.getByRole("button", { name: "Picture" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask Amelia" }));
    expect(screen.getByRole("button", { name: "Shock" })).toBeDisabled();
    rerender(<AmeliaRail featureId="fin.moneyleaks" hint="Recorded tracker" />);
    await act(async () => resolve(answer));
    expect(screen.queryByText(/Your recorded debt needs/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Picture" }));
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("Bills tab");
  });

  it("keeps the prompt after a failure so it can be retried", async () => {
    vi.mocked(askAmelia).mockRejectedValueOnce(new Error("Try again"));
    render(<AmeliaRail featureId="fin.debt" hint="Recorded tracker" />);
    fireEvent.click(screen.getByRole("button", { name: "Picture" }));
    fireEvent.click(screen.getByRole("button", { name: "Ask Amelia" }));
    expect(await screen.findByText("Try again")).toBeInTheDocument();
    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("Loans & Health");
    expect(screen.getByRole("button", { name: "Ask Amelia" })).toBeEnabled();
  });
});
