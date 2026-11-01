import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { humanSkill } from "../lib/format";
import { contract, fixed4, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const detail = contract.request_detail;
const ID = detail.request_id;
const base = {
  "GET /api/session": { body: MANAGER_SESSION },
  [`GET /api/staffing/requests/${ID}`]: { body: detail },
  "POST /api/identity/resolve": { body: { resolved: [] } },
};

describe("requests (real API contract payloads)", () => {
  it("lists request id, status, requirements and counts exactly as returned", async () => {
    mockApi({ ...base, "GET /api/staffing/requests": { body: contract.requests } });
    renderApp("/requests");
    const row = await screen.findByTestId(`request-${ID}`);
    const summary = contract.requests.requests[0];
    expect(within(row).getByText(ID)).toBeTruthy();
    expect(within(row).getByText("Open")).toBeTruthy();
    for (const [skill, lvl] of Object.entries(summary.requirements.required_skills)) {
      expect(within(row).getByText(`${humanSkill(skill)} · L${lvl}`)).toBeTruthy();
    }
    expect(within(row).getByText(String(summary.candidate_count))).toBeTruthy();
    expect(within(row).getByText(String(summary.excluded_count))).toBeTruthy();
  });

  it("labels a request created by an opportunity match as ranking only, never as approved staffing", async () => {
    const hoiReq = { ...contract.requests.requests[0], request_id: "hoi-mr_abc-1" };
    mockApi({ ...base, "GET /api/staffing/requests": { body: { requests: [hoiReq, contract.requests.requests[0]] } } });
    renderApp("/requests");
    const row = await screen.findByTestId("request-hoi-mr_abc-1");
    expect(within(row).getByText(/ranking only, not an approved staffing decision/)).toBeTruthy();
    expect(within(await screen.findByTestId(`request-${ID}`)).queryByText(/ranking only/)).toBeNull();
  });

  it("shows an empty state when there are no requests", async () => {
    mockApi({ ...base, "GET /api/staffing/requests": { body: { requests: [] } } });
    renderApp("/requests");
    expect(await screen.findByText("No staffing requests yet")).toBeTruthy();
  });

  it("renders candidates in API order with API fitness and API exclusion reasons", async () => {
    mockApi(base);
    renderApp(`/requests/${ID}`);
    await screen.findAllByTestId("ranked-row");
    expect(screen.getAllByTestId("ranked-identity").map((e) => e.textContent)).toEqual(detail.result.candidates.map((c) => c.coded_identity));
    expect(screen.getAllByTestId("ranked-fitness").map((e) => e.textContent)).toEqual(detail.result.candidates.map((c) => fixed4(c.fitness_score)));
    expect(screen.getAllByTestId("excluded-reason").map((e) => e.textContent)).toEqual(detail.result.excluded_candidates.map((e) => e.reason));
    expect(screen.getAllByText("Identity protected")).toHaveLength(detail.result.candidates.length);
  });

  it("never re-sorts: a deliberately unsorted payload is shown in payload order", async () => {
    const reversed = { ...detail, result: { ...detail.result, candidates: [...detail.result.candidates].reverse() } };
    mockApi({ ...base, [`GET /api/staffing/requests/${ID}`]: { body: reversed } });
    renderApp(`/requests/${ID}`);
    await screen.findAllByTestId("ranked-row");
    expect(screen.getAllByTestId("ranked-identity").map((e) => e.textContent)).toEqual(reversed.result.candidates.map((c) => c.coded_identity));
  });

  it("shows an empty state for a request without a stored ranking", async () => {
    mockApi({ ...base, [`GET /api/staffing/requests/${ID}`]: { body: { ...detail, result: {} } } });
    renderApp(`/requests/${ID}`);
    expect(await screen.findByText("No stored ranking")).toBeTruthy();
  });

  it("renders a 403 for another manager's request", async () => {
    mockApi({ ...base, [`GET /api/staffing/requests/${ID}`]: { status: 403, body: { detail: "x", error: "request_not_owned" } } });
    renderApp(`/requests/${ID}`);
    expect(await screen.findByText("Not authorized")).toBeTruthy();
    expect(screen.getByText(/belongs to another manager/)).toBeTruthy();
  });

  it("on synthetic data, auto-resolves shortlist names without a click", async () => {
    const names = detail.result.candidates.map((c, i) => ({ coded_identity: c.coded_identity, display_name: `Synthetic Person ${i + 1}`, rank: String(i + 1), fitness_score: "0.0" }));
    const calls = mockApi({ ...base, "POST /api/identity/resolve": { body: { resolved: names } } });
    renderApp(`/requests/${ID}`);
    await waitFor(() => expect(screen.getAllByTestId("resolved-name")).toHaveLength(names.length));
    expect(screen.getAllByTestId("resolved-name").map((e) => e.textContent)).toEqual(names.map((n) => n.display_name));
    expect(screen.getAllByTestId("ranked-identity").map((e) => e.textContent)).toEqual(detail.result.candidates.map((c) => c.coded_identity));
    expect(screen.queryByText("Identity protected")).toBeNull();
    expect(screen.queryByRole("button", { name: /Resolve shortlist identities/ })).toBeNull();
    const select = (await screen.findByRole("combobox", { name: "Candidate" })) as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(
      names.map((n, i) => `#${detail.result.candidates[i].rank} · ${n.display_name}`),
    );
    expect(calls.find((c) => c.path === "/api/identity/resolve")?.body).toEqual({ request_id: ID });
    expect(localStorage.length).toBe(0);
    expect(sessionStorage.getItem("hermes.token")).toBeTruthy();
  });

  it("on real data, keeps identities protected until the manager resolves", async () => {
    const names = detail.result.candidates.map((c, i) => ({ coded_identity: c.coded_identity, display_name: `Synthetic Person ${i + 1}`, rank: String(i + 1), fitness_score: "0.0" }));
    const calls = mockApi({
      "GET /api/session": { body: contract.real_session_manager },
      [`GET /api/staffing/requests/${ID}`]: { body: detail },
      "POST /api/identity/resolve": { body: { resolved: names } },
    });
    renderApp(`/requests/${ID}`);
    expect((await screen.findAllByText("Identity protected")).length).toBeGreaterThan(0);
    expect(screen.queryAllByTestId("resolved-name")).toHaveLength(0);
    expect(calls.filter((c) => c.path === "/api/identity/resolve")).toHaveLength(0);
    fireEvent.click(await screen.findByRole("button", { name: /Resolve shortlist identities/ }));
    await waitFor(() => expect(screen.getAllByTestId("resolved-name")).toHaveLength(names.length));
    expect(screen.getAllByTestId("resolved-name").map((e) => e.textContent)).toEqual(names.map((n) => n.display_name));
  });

  it.each([
    [429, undefined, "Too many identity resolutions"],
    [403, undefined, "not authorized"],
    [401, undefined, "session has expired"],
  ])("renders resolve failure %i without revealing names", async (status, code, text) => {
    mockApi({ ...base, "POST /api/identity/resolve": { status, body: { detail: "denied", error: code } } });
    renderApp(`/requests/${ID}`);
    if (status === 401) {
      expect(await screen.findByText("Sign in")).toBeTruthy();
      return;
    }
    expect((await screen.findByRole("alert")).textContent).toMatch(new RegExp(text, "i"));
    expect(screen.queryAllByTestId("resolved-name")).toHaveLength(0);
  });

  it("offers only shortlisted candidates and never sends owner or approved_by", async () => {
    let sent: unknown;
    mockApi({
      ...base,
      [`POST /api/staffing/${ID}/decision`]: (call) => {
        sent = call.body;
        return { body: {} };
      },
    });
    renderApp(`/requests/${ID}`);
    const select = (await screen.findByRole("combobox", { name: "Candidate" })) as HTMLSelectElement;
    expect([...select.options].map((o) => o.value)).toEqual(detail.result.candidates.map((c) => c.coded_identity));
    for (const excluded of detail.result.excluded_candidates) {
      expect([...select.options].map((o) => o.value)).not.toContain(excluded.coded_identity);
    }
    fireEvent.click(screen.getByRole("button", { name: "Choose this person" }));
    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toEqual({ status: "accepted", chosen_coded_identity: detail.result.candidates[0].coded_identity });
  });

  it.each([
    [422, "candidate_not_shortlisted", "Candidate is not in the shortlist."],
    [422, "candidate_excluded", "excluded by the engine"],
    [409, "request_state_conflict", "already been recorded"],
    [403, "request_not_owned", "belongs to another manager"],
  ])("renders decision error %i %s cleanly", async (status, code, text) => {
    mockApi({ ...base, [`POST /api/staffing/${ID}/decision`]: { status, body: { detail: "server detail", error: code } } });
    renderApp(`/requests/${ID}`);
    fireEvent.click(await screen.findByRole("button", { name: "Choose this person" }));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain(text);
    expect(alert.textContent).toContain(String(status));
  });

  it("shows the recorded decision for a decided request instead of the form", async () => {
    const decided = {
      ...detail,
      status: "accepted",
      decision: { status: "accepted", approved_by: "demo-manager", decided_at: "2026-01-01T00:00:00Z", chosen_coded_identity: detail.result.candidates[0].coded_identity, engine_rank_of_choice: 1 },
    };
    mockApi({ ...base, [`GET /api/staffing/requests/${ID}`]: { body: decided } });
    renderApp(`/requests/${ID}`);
    const panel = await screen.findByRole("region", { name: "Decision" });
    expect(within(panel).getByText(detail.result.candidates[0].coded_identity)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Choose this person" })).toBeNull();
  });

  it("find capability posts the form to the rank endpoint and opens the stored request", async () => {
    const calls = mockApi({
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/skills": { body: contract.skills },
      "GET /api/roles": { body: contract.roles },
      "POST /api/fitness/rank": { body: contract.rank_response },
      [`GET /api/staffing/requests/${ID}`]: { body: detail },
      "POST /api/identity/resolve": { body: { resolved: [] } },
    });
    renderApp("/capability");
    const idInput = (await screen.findByRole("textbox", { name: /Request id/i })) as HTMLInputElement;
    fireEvent.change(idInput, { target: { value: ID } });
    fireEvent.click(screen.getByRole("button", { name: "Find people" }));
    await screen.findAllByTestId("ranked-row");
    const body = calls.find((c) => c.path === "/api/fitness/rank")?.body as Record<string, unknown>;
    expect(body.request_id).toBe(ID);
    expect(Object.keys(body).sort()).toEqual(["critical_skills", "min_coverage_ratio", "request_id", "required_skills", "role_id", "shortlist_size"]);
    expect(body).not.toHaveProperty("requester_id");
  });

  it("renders rank validation errors from the server", async () => {
    mockApi({
      "GET /api/session": { body: MANAGER_SESSION },
      "GET /api/skills": { body: contract.skills },
      "GET /api/roles": { body: contract.roles },
      "POST /api/fitness/rank": { status: 409, body: { detail: "decided", error: "request_state_conflict" } },
    });
    renderApp("/capability");
    fireEvent.click(await screen.findByRole("button", { name: "Find people" }));
    expect((await screen.findByRole("alert")).textContent).toContain("already been recorded");
  });
});
