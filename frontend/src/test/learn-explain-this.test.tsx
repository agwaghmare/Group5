import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExplainThis } from "@/components/learn/explain-this";
import { learnApi } from "@/lib/learn-api";
import { writeCustomerSession } from "@/lib/customer-session";

vi.mock("@/lib/learn-api", () => ({
  learnUserId: () => "test-learner",
  learnApi: { prompts: vi.fn(), explain: vi.fn() },
}));
vi.mock("@/components/learn/explanation-card", () => ({ ExplanationCard: () => <p>Worked example</p> }));

function open() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return render(<QueryClientProvider client={client}><ExplainThis onOpenLesson={vi.fn()} /></QueryClientProvider>);
}

describe("Learn personal context", () => {
  beforeEach(() => {
    vi.mocked(learnApi.prompts).mockReset();
    vi.mocked(learnApi.explain).mockReset();
    vi.mocked(learnApi.prompts).mockResolvedValue({ prompts: [], notes: [] });
    writeCustomerSession({ email: "learner@example.test", provider: "email", customerId: "1007", token: "test-session" });
  });
  afterEach(() => { cleanup(); writeCustomerSession(null); });

  it("uses the signed-in account rather than defaulting to tracker 1000", async () => {
    open();
    await waitFor(() => expect(learnApi.prompts).toHaveBeenCalledWith(undefined, 1007));
    expect(screen.getByText(/signed-in finance tracker \(1007\)/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Finance tracker user/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Use sample numbers" }));
    await waitFor(() => expect(learnApi.prompts).toHaveBeenLastCalledWith(undefined, undefined));
  });

  it("shows Wilbur's reply to a personal question", async () => {
    vi.mocked(learnApi.explain).mockResolvedValue({
      matched: false, explanation: {} as never, notes: [],
      wilbur: { agent: "Wilbur", answer: "Compounding means earning interest on previous interest.", reasons: [], limitations: [] },
    });
    open();
    fireEvent.change(screen.getByLabelText("Ask Wilbur"), { target: { value: "Explain APY" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Wilbur" }));
    await waitFor(() => expect(learnApi.explain).toHaveBeenCalledWith(expect.objectContaining({
      tracker_user_id: 1007, question: "Explain APY",
    })));
    expect(await screen.findByRole("region", { name: "Wilbur's explanation" })).toBeInTheDocument();
    expect(screen.getByText(/Compounding means/)).toBeInTheDocument();
  });

  it("shows outside-lesson sources without the curriculum fallback card", async () => {
    vi.mocked(learnApi.explain).mockResolvedValue({
      matched: true, answer_mode: "web", explanation: {} as never, notes: [],
      wilbur: { agent: "Wilbur", answer: "Sharpe ratio compares excess return with volatility.", reasons: [], limitations: [],
        sources: [{ title: "Sharpe ratio", publisher: "Wikipedia", url: "https://en.wikipedia.org/wiki/Sharpe_ratio" }],
        google_search_url: "https://www.google.com/search?q=sharpe+ratio", web_status: "found" },
    });
    open();
    fireEvent.change(screen.getByLabelText("Ask Wilbur"), { target: { value: "What is Sharpe ratio?" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask Wilbur" }));
    expect(await screen.findByRole("link", { name: /Sharpe ratio.*Wikipedia/ })).toHaveAttribute("href", "https://en.wikipedia.org/wiki/Sharpe_ratio");
    expect(screen.getByRole("link", { name: "Search this topic on Google" })).toBeInTheDocument();
    expect(screen.queryByText("Worked example")).not.toBeInTheDocument();
    expect(learnApi.explain).toHaveBeenCalledWith(expect.objectContaining({ web_search: true }));
  });
});
