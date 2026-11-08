import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { learnApi } from "@/lib/learn-api";
import { writeCustomerSession } from "@/lib/customer-session";

describe("Learn session forwarding", () => {
  const fetchMock = vi.fn();
  beforeEach(() => {
    writeCustomerSession(null);
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockReset();
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({}) });
  });
  afterEach(() => { writeCustomerSession(null); vi.unstubAllGlobals(); });

  it("sends the signed-in token for personal prompts and Wilbur questions", async () => {
    writeCustomerSession({ email: "learner@example.test", provider: "email", customerId: "1007", token: "test-session" });
    await learnApi.prompts(undefined, 1007);
    await learnApi.explain({ question_id: "explain-apy", tracker_user_id: 1007 });
    const [promptUrl, promptInit] = fetchMock.mock.calls[0]!;
    const [agentUrl, agentInit] = fetchMock.mock.calls[1]!;
    expect(promptUrl).toContain("tracker_user_id=1007");
    expect(promptInit.headers.get("Authorization")).toBe("Bearer test-session");
    expect(agentUrl).toBe("/api/learn/wilbur");
    expect(agentInit.headers.get("Authorization")).toBe("Bearer test-session");
    expect(JSON.parse(agentInit.body).tracker_user_id).toBe(1007);
  });

  it("keeps anonymous lesson examples available without claiming a live agent", async () => {
    await learnApi.explain({ question_id: "explain-apy" });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/learn/context/explain");
    expect(fetchMock.mock.calls[0]![1].headers.has("Authorization")).toBe(false);
  });

  it("does not make another model call when opening the deterministic deeper example", async () => {
    writeCustomerSession({ email: "learner@example.test", provider: "email", token: "test-session" });
    await learnApi.explain({ question_id: "explain-apy", go_deeper: true });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/learn/context/explain");
    expect(fetchMock.mock.calls[0]![1].headers.get("Authorization")).toBe("Bearer test-session");
  });
});
