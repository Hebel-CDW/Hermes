import { describe, expect, it, vi } from "vitest";
import { ApiError, apiFetch, humanMessage, setToken, UNAUTHORIZED_EVENT } from "../api/http";
import { mockApi } from "./harness";

describe("http client", () => {
  it.each([
    [401, "Your session has expired or is invalid. Sign in again."],
    [403, "You're not authorized to view or perform this action."],
    [404, "Not found."],
    [409, "This action conflicts with the current state of the request."],
    [429, "Too many identity resolutions. Wait a minute and try again."],
    [500, "The server encountered an error."],
    [503, "The service is unavailable: the database was not trusted by the server."],
  ])("maps HTTP %i to a human message", (status, message) => {
    expect(humanMessage(status, undefined, "")).toBe(message);
  });

  it("prefers governance error codes over generic status text", () => {
    expect(humanMessage(422, "candidate_not_shortlisted", "x")).toBe("Candidate is not in the shortlist.");
    expect(humanMessage(403, "request_not_owned", "")).toMatch(/belongs to another manager/);
    expect(humanMessage(409, "request_state_conflict", "")).toMatch(/already been recorded/);
  });

  it("surfaces pydantic 422 detail without the 'Value error' prefix", async () => {
    mockApi({ "POST /api/fitness/rank": { status: 422, body: { detail: [{ msg: "Value error, unknown skill ids: ['x']" }] } } });
    const err = (await apiFetch("/api/fitness/rank", { method: "POST", body: "{}" }).catch((e: unknown) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(422);
    expect(err.message).toBe("Invalid input: unknown skill ids: ['x']");
  });

  it("sends only the bearer token — never role, identity or owner headers", async () => {
    const calls = mockApi({ "GET /api/overview": { body: {} } });
    setToken("tok");
    await apiFetch("/api/overview");
    expect(calls[0].headers).toEqual({ "Content-Type": "application/json", Authorization: "Bearer tok" });
  });

  it("signals sign-out when the server rejects a stored token", async () => {
    mockApi({ "GET /api/session": { status: 401, body: { detail: "expired", error: "unauthenticated" } } });
    setToken("stale");
    const listener = vi.fn();
    window.addEventListener(UNAUTHORIZED_EVENT, listener);
    await apiFetch("/api/session").catch(() => undefined);
    window.removeEventListener(UNAUTHORIZED_EVENT, listener);
    expect(listener).toHaveBeenCalledTimes(1);
  });
});
