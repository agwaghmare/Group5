import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PortfolioWorkspace } from "@/components/employee/portfolio-workspace";
import { staffFetch } from "@/lib/staff-api";

vi.mock("@/lib/staff-api", () => ({ staffFetch: vi.fn() }));
vi.mock("recharts", async (importOriginal) => ({
  ...(await importOriginal<typeof import("recharts")>()),
  ResponsiveContainer: () => <div data-testid="return-chart" />,
}));
const allocations = { stocks: 0.45, bonds: 0.4, foreign: 0.15 };
const assessment = {
  allocations,
  metrics: { volatility: 0.09, annualized_return: 0.04 },
  risk_budget: 0.12,
};
const detail = {
  client_id: 1000,
  name: "Client One",
  revision: 1,
  value_cents: 1000000,
  as_of: "2026-10-31",
  allocations,
  profile: {
    tolerance: 3,
    goal: "Long-term goals",
    horizon_months: 120,
    liquidity_need_cents: 0,
    target_return: 0.05,
    questionnaire: { source: "Synthetic questionnaire" },
  },
  holdings: [
    {
      bucket: "stocks",
      instrument: "Domestic stock model",
      asset_class: "stock",
      geography: "domestic",
      currency: "USD",
      value_cents: 450000,
      units: 20,
    },
  ],
  assessment: null,
  history: [],
  financial_history: [],
  behavior: { note: "Trade history unavailable", snapshot_count: 0 },
  proposals: [
    {
      id: "RP-1",
      base_revision: 1,
      status: "proposed",
      before: assessment,
      after: {
        ...assessment,
        allocations: { stocks: 0.35, bonds: 0.5, foreign: 0.15 },
      },
      rationale: "Reduce risk within the client budget",
      estimated_cost_cents: 200,
      cost_assumption: "Synthetic costs",
      goal_feasible: false,
      trades: [
        { bucket: "stocks", delta_cents: -20000 },
        { bucket: "bonds", delta_cents: 20000 },
      ],
    },
  ],
};
function mount(onContext = vi.fn()) {
  const cache = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={cache}>
      <PortfolioWorkspace focused onContext={onContext} />
    </QueryClientProvider>,
  );
}
beforeEach(() => {
  vi.mocked(staffFetch).mockReset();
});
afterEach(cleanup);

describe("Portfolio risk workspace", () => {
  it("updates the assigned portfolio overview after assignment and assessment", async () => {
    let assigned = false;
    let assessed = false;
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/summary")
        return {
          assigned_clients: assigned ? 5 : 4,
          assessed_clients: assessed ? 5 : 4,
          needs_assessment: assigned && !assessed ? 1 : 0,
          above_risk_budget: 0,
          within_risk_budget: assessed ? 5 : 4,
          clients_with_pending_previews: 0,
          mean_volatility: assessed ? 0.05 : null,
          mean_annualized_return: assessed ? 0.03 : null,
          aggregate_contributors: assessed ? 5 : 4,
          suppression_threshold: 5,
          aggregate_note: "Averages require five current assessments",
          method: "Latest saved portfolio assessments",
        };
      if (path === "/portfolio/clients")
        return {
          clients: Array.from({ length: assigned ? 5 : 4 }, (_, i) => ({
            client_id: 1000 + i,
            name: `Client ${i + 1}`,
          })),
        };
      if (path.startsWith("/portfolio/unassigned"))
        return {
          clients: assigned ? [] : [{ client_id: 1004, name: "Client Five" }],
        };
      if (path === "/portfolio/assignments") {
        assigned = true;
        return { assigned: true };
      }
      if (path.endsWith("/assessments")) {
        assessed = true;
        return {};
      }
      return { ...detail, client_id: 1004, name: "Client Five" };
    });
    mount();
    const heading = screen.getByText("Assigned portfolio overview");
    fireEvent.click(heading);
    const panel = within(heading.closest("details")!);
    await waitFor(() =>
      expect(
        panel.getByText("Assigned clients").parentElement,
      ).toHaveTextContent("4"),
    );
    expect(panel.queryByText("Tracker clients")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Assign client" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Assign to me" }),
    );
    await waitFor(() =>
      expect(
        panel.getByText("Assigned clients").parentElement,
      ).toHaveTextContent("5"),
    );
    expect(
      panel.getByText("Current assessments").parentElement,
    ).toHaveTextContent("4");
    const assessButton = await screen.findByRole("button", {
      name: "Run risk assessment",
    });
    await waitFor(() => expect(assessButton).not.toBeDisabled());
    fireEvent.click(assessButton);
    await waitFor(() =>
      expect(
        panel.getByText("Current assessments").parentElement,
      ).toHaveTextContent("5"),
    );
    expect(
      panel.getByText("Mean portfolio volatility").parentElement,
    ).toHaveTextContent("5.00%");
    expect(
      panel.getByText("Mean modeled annual return").parentElement,
    ).toHaveTextContent("3.00%");
  });

  it("refreshes the saved allocation and metrics after approval and a subsequent assessment rerun", async () => {
    let applied = false;
    const updated = {
      ...assessment,
      metrics: {
        volatility: 0.04,
        annualized_return: 0.025,
        max_drawdown: -0.04,
        total_return: 0.13,
      },
      benchmark: { annualized_return: 0.03 },
      risk_capacity: "moderate",
      flags: [],
      return_history: [],
      limitations: [],
      financial_context: {
        monthly_income: 5000,
        monthly_surplus: 1000,
        emergency_fund_months: 6,
        income_volatility: 0.1,
        finance_as_of: "2026-10-31",
      },
      window_start: "2021-10-31",
      data_as_of: "2026-10-31",
      method: "Test historical model",
    };
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients")
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (path.endsWith("/approve")) {
        applied = true;
        return { approved: true, revision: 2 };
      }
      if (path.endsWith("/assessments")) return updated;
      return {
        ...detail,
        revision: applied ? 2 : 1,
        allocations: applied
          ? detail.proposals[0]!.after.allocations
          : detail.allocations,
        assessment: applied
          ? updated
          : {
              ...updated,
              metrics: {
                ...updated.metrics,
                volatility: 0.09,
                annualized_return: 0.04,
              },
            },
        proposals: applied
          ? [{ ...detail.proposals[0], status: "approved" }]
          : detail.proposals,
      };
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    fireEvent.change(screen.getByLabelText("Rebalance rationale"), {
      target: { value: "Approve the reviewed changed allocation." },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", { name: "Approve simulated rebalance" }),
    );
    await screen.findByText(
      "Simulated rebalance approved. No orders were sent.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Overview" }));
    expect(screen.getByText("50.00%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Risk & returns" }));
    expect(
      screen.getByText("Annualized modeled return").parentElement,
    ).toHaveTextContent("2.50%");
    expect(
      screen.getByText("Annualized volatility").parentElement,
    ).toHaveTextContent("4.00%");
    fireEvent.click(
      screen.getByRole("button", { name: "Run risk assessment" }),
    );
    await screen.findByText("Risk assessment saved.");
    expect(
      screen.getByText("Annualized modeled return").parentElement,
    ).toHaveTextContent("2.50%");
    expect(
      screen.getByText("Annualized volatility").parentElement,
    ).toHaveTextContent("4.00%");
  });

  it("keeps custom percentages visible when the preview exceeds portfolio limits", async () => {
    const unsafe = {
      ...detail.proposals[0]!,
      id: "RP-BLOCKED",
      approval_allowed: false,
      after: {
        ...assessment,
        allocations: { stocks: 0.9, bonds: 0.05, foreign: 0.05 },
        metrics: { ...assessment.metrics, volatility: 0.18 },
      },
      constraint_violations: [
        {
          code: "concentration",
          message: "Concentration limit exceeded",
          actual: 0.9,
          limit: 0.8,
        },
      ],
    };
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients")
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (path.endsWith("/proposals")) return unsafe;
      return detail;
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    fireEvent.change(screen.getByLabelText("Rebalance rationale"), {
      target: { value: "Compare a more concentrated allocation." },
    });
    fireEvent.change(screen.getByLabelText("Domestic stocks (%)"), {
      target: { value: "90" },
    });
    fireEvent.change(screen.getByLabelText("Domestic bonds (%)"), {
      target: { value: "5" },
    });
    fireEvent.change(screen.getByLabelText("Foreign-market equities (%)"), {
      target: { value: "5" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Preview my allocation" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "approval blocked",
    );
    expect(screen.getByLabelText("Domestic stocks (%)")).toHaveValue(90);
    expect(screen.getByLabelText("Domestic bonds (%)")).toHaveValue(5);
    expect(screen.getByLabelText("Foreign-market equities (%)")).toHaveValue(5);
    const proposed = screen.getByRole("heading", { name: "Proposed" });
    expect(
      within(proposed.parentElement!).getByText("90.00%"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Approve simulated rebalance" }),
    ).toBeDisabled();
  });

  it("previews edited allocation values and displays the exact returned proposal", async () => {
    const preview = {
      ...detail.proposals[0]!,
      id: "RP-2",
      rationale: "My manually edited allocation",
      after: {
        ...assessment,
        allocations: { stocks: 0.2, bonds: 0.7, foreign: 0.1 },
      },
    };
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients")
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (path.endsWith("/proposals")) return preview;
      return detail;
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    fireEvent.change(screen.getByLabelText("Rebalance rationale"), {
      target: { value: "My manually edited allocation" },
    });
    fireEvent.change(screen.getByLabelText("Domestic stocks (%)"), {
      target: { value: "20" },
    });
    fireEvent.change(screen.getByLabelText("Domestic bonds (%)"), {
      target: { value: "70" },
    });
    fireEvent.change(screen.getByLabelText("Foreign-market equities (%)"), {
      target: { value: "10" },
    });
    expect(
      screen.queryByRole("heading", {
        name: "Review proposal before approval",
      }),
    ).toBeNull();
    expect(
      screen.queryByRole("button", { name: "Approve simulated rebalance" }),
    ).toBeNull();
    fireEvent.click(
      screen.getByRole("button", { name: "Preview my allocation" }),
    );
    const proposed = await screen.findByRole("heading", { name: "Proposed" });
    expect(
      within(proposed.parentElement!).getByText("70.00%"),
    ).toBeInTheDocument();
    expect(staffFetch).toHaveBeenCalledWith(
      "/portfolio/clients/1000/proposals",
      expect.objectContaining({
        body: {
          rationale: "My manually edited allocation",
          allocations: {
            stocks: "0.200000",
            bonds: "0.700000",
            foreign: "0.100000",
          },
        },
      }),
    );
  });

  it("hides the old proposal after a rejected custom allocation", async () => {
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients")
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (path.endsWith("/proposals"))
        throw new Error("Proposed allocation exceeds the risk budget");
      return detail;
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    fireEvent.change(screen.getByLabelText("Rebalance rationale"), {
      target: { value: "A different allocation for review" },
    });
    fireEvent.change(screen.getByLabelText("Domestic stocks (%)"), {
      target: { value: "80" },
    });
    fireEvent.change(screen.getByLabelText("Domestic bonds (%)"), {
      target: { value: "10" },
    });
    fireEvent.change(screen.getByLabelText("Foreign-market equities (%)"), {
      target: { value: "10" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Preview my allocation" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "exceeds the risk budget",
    );
    expect(
      screen.queryByRole("heading", {
        name: "Review proposal before approval",
      }),
    ).toBeNull();
  });

  it("shows an unchanged allocation without trades or an approval action", async () => {
    vi.mocked(staffFetch).mockImplementation(async (path) =>
      path === "/portfolio/clients"
        ? { clients: [{ client_id: 1000, name: "Client One" }] }
        : {
            ...detail,
            proposals: [
              {
                ...detail.proposals[0],
                no_change: true,
                after: assessment,
                trades: [{ bucket: "stocks", delta_cents: 0 }],
              },
            ],
          },
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    expect(screen.getByText(/No allocation change/)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Approve simulated rebalance" }),
    ).toBeNull();
    expect(screen.queryByText(/Buy Domestic stocks/)).toBeNull();
  });

  it("confirms a profile save beside the form and refreshes risk and goal comparisons", async () => {
    const calculated = {
      ...assessment,
      benchmark: { ...assessment.metrics, annualized_return: 0.03 },
      metrics: { ...assessment.metrics, total_return: 0.2, max_drawdown: -0.1 },
      risk_capacity: "moderate",
      stated_tolerance: 3,
      flags: [],
      financial_context: {
        monthly_income: 5000,
        monthly_surplus: 1000,
        emergency_fund_months: 6,
        income_volatility: 0.1,
        finance_as_of: "2026-10-31",
      },
      return_history: [],
      limitations: [],
      method: "Historical constant-mix model",
      window_start: "2021-10-31",
      data_as_of: "2026-10-31",
    };
    let saved = false;
    vi.mocked(staffFetch).mockImplementation(async (path, init) => {
      if (path === "/portfolio/clients")
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (init?.method === "PUT") {
        saved = true;
        return { saved: true };
      }
      return {
        ...detail,
        revision: saved ? 2 : 1,
        profile: {
          ...detail.profile,
          tolerance: saved ? 1 : 3,
          target_return: saved ? 0.1 : 0.05,
        },
        assessment: {
          ...calculated,
          risk_budget: saved ? 0.06 : 0.12,
          stated_tolerance: saved ? 1 : 3,
          risk_limits: {
            financial_capacity: 0.12,
            stated_tolerance: saved ? 0.06 : 0.12,
            investment_horizon: 0.2,
            liquidity_need: null,
          },
          binding_limits: saved
            ? ["stated_tolerance"]
            : ["financial_capacity", "stated_tolerance"],
          profile_model: {
            allocations: saved
              ? { stocks: 0.15, bonds: 0.75, foreign: 0.1 }
              : allocations,
            metrics: {
              ...calculated.metrics,
              volatility: saved ? 0.05 : 0.09,
              annualized_return: saved ? 0.02 : 0.04,
            },
            goal_feasible: false,
            requires_approval: true,
          },
        },
      };
    });
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Profile" }));
    fireEvent.change(screen.getByLabelText(/Stated risk tolerance/), {
      target: { value: "1" },
    });
    fireEvent.change(screen.getByLabelText("Annual return goal (%)"), {
      target: { value: "10" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save investment profile" }),
    );
    expect(
      await screen.findByText(
        "Profile saved. Risk assessment and goal comparisons updated.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/Stated risk tolerance/)).toHaveValue(1);
    fireEvent.click(screen.getByRole("button", { name: "Risk & returns" }));
    expect(screen.getByText("Risk budget").parentElement).toHaveTextContent(
      "6.00%",
    );
    expect(
      screen.getByText("Annual return goal").parentElement,
    ).toHaveTextContent("10.00%");
    expect(
      screen.getByText("Annualized modeled return").parentElement,
    ).toHaveTextContent("4.00%");
    expect(
      screen.getByText("Suggested volatility").parentElement,
    ).toHaveTextContent("5.00%");
    expect(
      screen.getByText("Suggested annualized return").parentElement,
    ).toHaveTextContent("2.00%");
    expect(
      screen.getByText(/Binding limit: stated tolerance/),
    ).toBeInTheDocument();
  });

  it("assigns an unassigned client and sends that client context to Bessie", async () => {
    let assigned = false;
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients")
        return {
          clients: assigned ? [{ client_id: 1000, name: "Client One" }] : [],
        };
      if (path.startsWith("/portfolio/unassigned"))
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      if (path === "/portfolio/assignments") {
        assigned = true;
        return { assigned: true };
      }
      return detail;
    });
    const onContext = vi.fn();
    mount(onContext);
    expect(await screen.findByText(/Your queue is empty/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Assign client" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Assign to me" }),
    );
    expect(
      await screen.findByRole("heading", { name: "Client One" }),
    ).toBeInTheDocument();
    expect(staffFetch).toHaveBeenCalledWith(
      "/portfolio/assignments",
      expect.objectContaining({ body: { client_id: 1000 } }),
    );
    await waitFor(() =>
      expect(onContext).toHaveBeenCalledWith(
        expect.objectContaining({
          featureId: "staff.portfolio",
          resourceId: "1000",
        }),
      ),
    );
    expect(screen.getByText(/Performance is modeled/)).toBeInTheDocument();
  });

  it("requires explicit confirmation and a rationale before simulated approval", async () => {
    vi.mocked(staffFetch).mockImplementation(async (path) =>
      path === "/portfolio/clients"
        ? { clients: [{ client_id: 1000, name: "Client One" }] }
        : detail,
    );
    mount();
    fireEvent.click(await screen.findByRole("button", { name: /Client One/ }));
    await screen.findByRole("heading", { name: "Client One" });
    fireEvent.click(screen.getByRole("button", { name: "Rebalance" }));
    expect(
      screen.getByRole("button", { name: "Approve simulated rebalance" }),
    ).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Rebalance rationale"), {
      target: { value: "Reviewed this client's risk and allocation." },
    });
    expect(
      screen.getByRole("button", { name: "Approve simulated rebalance" }),
    ).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(
      screen.getByRole("button", { name: "Approve simulated rebalance" }),
    );
    await waitFor(() =>
      expect(staffFetch).toHaveBeenCalledWith(
        "/portfolio/clients/1000/proposals/RP-1/approve",
        expect.objectContaining({
          body: {
            rationale: "Reviewed this client's risk and allocation.",
            confirm_simulated: true,
          },
        }),
      ),
    );
  });

  it("shows assignment failures without claiming the client was assigned", async () => {
    vi.mocked(staffFetch).mockImplementation(async (path) => {
      if (path === "/portfolio/clients") return { clients: [] };
      if (path.startsWith("/portfolio/unassigned"))
        return { clients: [{ client_id: 1000, name: "Client One" }] };
      throw new Error("Client is already assigned to another manager");
    });
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Assign client" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Assign to me" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "already assigned",
    );
    expect(screen.queryByText("Client assigned to your workspace.")).toBeNull();
  });
});
