import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PortfolioActivity } from "@/components/employee/portfolio-activity";
import { staffFetch } from "@/lib/staff-api";
vi.mock("@/lib/staff-api", () => ({ staffFetch: vi.fn() }));
beforeEach(() => {
  vi.mocked(staffFetch).mockReset();
});
afterEach(cleanup);
function mount() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <PortfolioActivity />
    </QueryClientProvider>,
  );
}
describe("Risk manager activity", () => {
  it("shows portfolio records and filters approved rebalances separately", async () => {
    vi.mocked(staffFetch).mockImplementation(async (path) => ({
      events: path.includes("?action=")
        ? []
        : [
            {
              id: "ACT-1",
              title: "Risk assessment saved",
              client_id: 1005,
              client_name: "Client Five",
              when: "2026-11-08T12:00:00Z",
              outcome: "allowed",
              detail: "Risk capacity: moderate. Portfolio revision 4.",
              fields: [{ label: "Volatility", value: "3.80%" }],
            },
          ],
    }));
    mount();
    expect(
      await screen.findByText("Risk assessment saved"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Client Five/)).toBeInTheDocument();
    expect(screen.queryByText(/Save progress.*Research/)).toBeNull();
    fireEvent.change(screen.getByLabelText("Activity type"), {
      target: { value: "portfolio_rebalance_approved" },
    });
    await waitFor(() =>
      expect(staffFetch).toHaveBeenCalledWith(
        "/portfolio/activity?action=portfolio_rebalance_approved",
      ),
    );
    expect(
      await screen.findByText(/No matching portfolio activity/),
    ).toBeInTheDocument();
  });
  it("reports a permission error without showing another manager's activity", async () => {
    vi.mocked(staffFetch).mockRejectedValue(
      new Error("Not available for your role"),
    );
    mount();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Not available for your role",
    );
    expect(
      screen.queryByRole("heading", { name: "Risk assessment saved" }),
    ).toBeNull();
  });
});
