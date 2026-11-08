import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/components/login-page";
import { RequireCustomer } from "@/components/require-customer";
import { writeCustomerSession } from "@/lib/customer-session";

const navigate = vi.hoisted(() => vi.fn());
vi.mock("@tanstack/react-router", () => ({ useNavigate: () => navigate }));

function mount(child: React.ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>{child}</QueryClientProvider>,
  );
}

beforeEach(() => {
  navigate.mockReset();
  window.sessionStorage.clear();
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Account sign in", () => {
  it("sends the entered password and opens the server-assigned employee workspace", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          token: "account-token",
          user: {
            email: "analyst@company.test",
            display_name: "Account Analyst",
            role: "credit_analyst",
            role_label: "Credit Analyst",
            customer_id: null,
            employee_id: "EMP-101",
            is_staff: true,
          },
        }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    mount(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "analyst@company.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "actual-account-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({ to: "/employee" }),
    );
    expect(JSON.parse(fetcher.mock.calls[0]![1].body)).toEqual({
      email: "analyst@company.test",
      password: "actual-account-password",
    });
    expect(screen.queryByText(/choose a demo persona/i)).toBeNull();
    expect(screen.queryByText(/continue with google/i)).toBeNull();
  });

  it("keeps an invalid account on the sign-in page", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(
            JSON.stringify({ detail: "Invalid email or password" }),
            { status: 401 },
          ),
        ),
    );
    mount(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), {
      target: { value: "analyst@company.test" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "wrong-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(
      await screen.findByText("Invalid email or password"),
    ).toBeInTheDocument();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("uses server identity to prevent employee access to a customer page", async () => {
    writeCustomerSession({
      email: "analyst@company.test",
      provider: "email",
      token: "valid-token",
      role: "customer",
      isStaff: false,
    });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ is_staff: true }), { status: 200 }),
        ),
    );
    mount(
      <RequireCustomer>
        <p>Customer finance</p>
      </RequireCustomer>,
    );
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith({ to: "/employee", replace: true }),
    );
    expect(screen.queryByText("Customer finance")).toBeNull();
  });
});
