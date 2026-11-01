import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { matchImport, parseLevel, parsePasted, toCsv } from "../lib/csv";
import { contract, DIRECTORY, EMPLOYEE_SESSION, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const REPORT = "EMP-c775791c"; // Jordan Lee
const SAM = EMPLOYEE_SESSION.coded_identity!; // EMP-f232ab6e

const claim = {
  request_id: "chg-11111111-1111-1111-1111-111111111111",
  coded_identity: REPORT,
  kind: "skill_claim",
  payload: { skill_id: "container_orchestration", proficiency: 4, note: "ran the migration" },
  status: "pending",
  created_at: "2026-10-05T10:00:00Z",
  decided_by: null,
  decided_at: null,
  decision_note: null,
  skill_name: "Container Orchestration",
};
const cert = {
  ...claim,
  request_id: "chg-22222222-2222-2222-2222-222222222222",
  kind: "certificate",
  payload: { cert_code: "CKA", earned_at: "2025-03-01T00:00:00+00:00", skill_id: "container_orchestration" },
};

const manager = {
  "GET /api/session": { body: MANAGER_SESSION },
  "GET /api/skills": { body: contract.skills },
  "GET /api/roles": { body: contract.roles },
  "GET /api/identity/directory": { body: DIRECTORY },
};

describe("csv helpers", () => {
  it("quotes cells and parses pasted spreadsheet rows", () => {
    expect(toCsv([["a", 'b,"c"'], [1, null]])).toBe('a,"b,""c"""\r\n1,');
    expect(parsePasted("Jordan Lee\tPython\t4\nSam; x; 2")).toEqual([
      ["Jordan Lee", "Python", "4"],
      ["Sam", "x", "2"],
    ]);
  });

  it("reads levels as numbers or words and refuses guesses", () => {
    expect(parseLevel("4")).toBe(4);
    expect(parseLevel("Level 3")).toBe(3);
    expect(parseLevel("L5")).toBe(5);
    expect(parseLevel("Expert")).toBe(5);
    expect(parseLevel("9")).toBeNull();
    expect(parseLevel("high")).toBeNull();
  });

  it("matches people and skills exactly and reports everything else", () => {
    const people = DIRECTORY.people;
    const skills = [{ skill_id: "python", name: "Python" }];
    const { items, problems } = matchImport(
      parsePasted("Person,Skill,Level\nJordan Lee,Python,4\nJordan Lee,Python,3\nNobody Here,Python,3\nAlex Rivera,Python,3\nJordan Lee,Cobol,2\nJordan Lee,Python,11"),
      people,
      skills,
      new Set([REPORT]),
    );
    expect(items).toEqual([{ line: 2, coded_identity: REPORT, skill_id: "python", proficiency: 4 }]);
    expect(problems.map((p) => p.reason)).toEqual([
      "Duplicate of an earlier row",
      'Person "Nobody Here" was not recognised',
      "Alex Rivera is not on your team",
      'Skill "Cobol" is not in the governed list',
      'Level "11" must be 1 to 5',
    ]);
  });
});

describe("Approvals", () => {
  it("shows what is waiting and approves with the level the manager confirms", async () => {
    const calls = mockApi({
      ...manager,
      "GET /api/team/inbox": { body: { requests: [claim, cert], contests: [] } },
      [`POST /api/team/inbox/${claim.request_id}/decide`]: { body: { ...claim, status: "approved" } },
    });
    renderApp("/inbox");
    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    const rows = await screen.findAllByTestId("inbox-row");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Jordan Lee")).toBeTruthy();
    expect(within(rows[0]).getByText(/ran the migration/)).toBeTruthy();

    fireEvent.change(within(rows[0]).getByLabelText("Level you confirm"), { target: { value: "3" } });
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.path === `/api/team/inbox/${claim.request_id}/decide`)).toBe(true));
    const posted = calls.find((c) => c.path === `/api/team/inbox/${claim.request_id}/decide`);
    expect(posted?.body).toEqual({ decision: "approve", proficiency: 3 });
    await waitFor(() => expect(screen.getAllByTestId("inbox-row")).toHaveLength(1));
  });

  it("approves a certificate with its date and can decline with a note", async () => {
    const calls = mockApi({
      ...manager,
      "GET /api/team/inbox": { body: { requests: [cert], contests: [] } },
      [`POST /api/team/inbox/${cert.request_id}/decide`]: { body: { ...cert, status: "declined" } },
    });
    renderApp("/inbox");
    const row = await screen.findByTestId("inbox-row");
    expect((within(row).getByLabelText("Date earned") as HTMLInputElement).value).toBe("2025-03-01");
    fireEvent.change(within(row).getByLabelText("Note to them"), { target: { value: "send the PDF" } });
    fireEvent.click(within(row).getByRole("button", { name: "Decline" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/decide"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/decide"))?.body).toEqual({ decision: "decline", note: "send the PDF" });
  });

  it("says so when nothing is waiting", async () => {
    mockApi({ ...manager, "GET /api/team/inbox": { body: { requests: [], contests: [] } } });
    renderApp("/inbox");
    expect(await screen.findByText("You are all caught up")).toBeTruthy();
  });

  it("is closed to employees", async () => {
    mockApi({ "GET /api/session": { body: EMPLOYEE_SESSION } });
    renderApp("/inbox");
    expect(await screen.findByText("Not available for your role")).toBeTruthy();
  });
});

describe("Bulk update", () => {
  const grid = {
    people: [REPORT],
    cells: { [REPORT]: { container_orchestration: { level: 2, confidence: 0.9, freshness: 0.5 } } },
  };
  const base = { ...manager, "GET /api/team/grid": { body: grid } };

  it("saves only the cells that changed, in one request", async () => {
    const calls = mockApi({ ...base, "POST /api/team/bulk-declare": { body: { saved: 1 } } });
    renderApp("/team-grid");
    const cell = (await screen.findByLabelText("Jordan Lee · Container Orchestration")) as HTMLSelectElement;
    expect(cell.value).toBe("2");
    fireEvent.change(cell, { target: { value: "4" } });
    fireEvent.click(await screen.findByRole("button", { name: "Save 1 change" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/team/bulk-declare")).toBe(true));
    expect(calls.find((c) => c.path === "/api/team/bulk-declare")?.body).toEqual({
      items: [{ coded_identity: REPORT, skill_id: "container_orchestration", proficiency: 4, note: "bulk update" }],
    });
  });

  it("discarding returns to the saved levels and writes nothing", async () => {
    const calls = mockApi(base);
    renderApp("/team-grid");
    const cell = (await screen.findByLabelText("Jordan Lee · Container Orchestration")) as HTMLSelectElement;
    fireEvent.change(cell, { target: { value: "5" } });
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    await waitFor(() => expect((screen.getByLabelText("Jordan Lee · Container Orchestration") as HTMLSelectElement).value).toBe("2"));
    expect(calls.some((c) => c.method === "POST")).toBe(false);
  });

  it("turns pasted rows into pending changes and lists the rows it could not use", async () => {
    mockApi(base);
    renderApp("/team-grid");
    await screen.findByLabelText("Jordan Lee · Container Orchestration");
    fireEvent.click(screen.getByRole("button", { name: "Paste from Excel" }));
    fireEvent.change(await screen.findByLabelText("Pasted rows"), {
      target: { value: "Jordan Lee\tContainer Orchestration\t5\nJordan Lee\tCobol\t3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Check rows and add to grid" }));
    expect(await screen.findByText("1 ready · 1 need attention")).toBeTruthy();
    expect(screen.getByText(/Skill "Cobol" is not in the governed list/)).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Save 1 change" })).toBeTruthy();
  });
});

describe("My growth", () => {
  const employee = {
    "GET /api/session": { body: EMPLOYEE_SESSION },
    "GET /api/skills": { body: contract.skills },
    "GET /api/roles": { body: contract.roles },
    "GET /api/identity/directory": { body: DIRECTORY },
    "GET /api/cert-catalog": { body: { certificates: [{ code: "CKA", skill_id: "container_orchestration", skill_name: "Container Orchestration" }] } },
    "GET /api/me/timeline": { body: { events: [{ seq: 4, at: "2026-10-05T10:00:00Z", event_type: "employee_request_submitted", title: "You sent a request to your manager", detail: "Container Orchestration" }] } },
  };

  it("lets the employee pick a goal, then shows the path to it", async () => {
    let goal: unknown = null;
    const calls = mockApi({
      ...employee,
      "GET /api/me/workflow": () => ({ body: { requests: [], goal } }),
      "PUT /api/me/goal": () => {
        goal = { ...contract.roles.roles[0], set_at: "2026-10-05T10:00:00Z" };
        return { body: goal };
      },
      "POST /api/fitness/gaps": {
        body: {
          coded_identity: SAM,
          role_id: "senior_cloud_engineer",
          scoring_config_version: "x",
          gaps: [
            { skill_id: "container_orchestration", required_level: 4, current_level: 4, demand_impact: 0.5, reasoning: "", evidence_ids: [] },
            { skill_id: "azure_networking", required_level: 4, current_level: 2, demand_impact: 0.5, reasoning: "", evidence_ids: [] },
          ],
        },
      },
    });
    renderApp("/growth");
    fireEvent.click(await screen.findByRole("button", { name: "Aim for Senior Cloud Engineer" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT" && c.path === "/api/me/goal")).toBe(true));
    expect((calls.find((c) => c.method === "PUT") as { body: unknown }).body).toEqual({ role_id: "senior_cloud_engineer" });
    expect(await screen.findByText("Your path to Senior Cloud Engineer")).toBeTruthy();
    expect(await screen.findByText("At the level")).toBeTruthy();
    expect(screen.getByText("2 levels to go")).toBeTruthy();
    expect(screen.getByRole("img", { name: /Skills at the level this role needs: 50%/ })).toBeTruthy();
  });

  it("sends a skill proposal that waits for the manager, and shows the timeline", async () => {
    const calls = mockApi({
      ...employee,
      "GET /api/me/workflow": { body: { requests: [], goal: null } },
      "POST /api/me/requests": { body: { ...claim, coded_identity: SAM } },
    });
    renderApp("/growth");
    await screen.findByText("Where do you want to grow?");
    fireEvent.change(screen.getByLabelText("Skill"), { target: { value: "azure_networking" } });
    fireEvent.change(screen.getByLabelText("Your level"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "led the cutover" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to my manager" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/me/requests")).toBe(true));
    expect(calls.find((c) => c.path === "/api/me/requests")?.body).toEqual({ kind: "skill_claim", skill_id: "azure_networking", proficiency: 4, note: "led the cutover" });
    expect(await screen.findByText("You sent a request to your manager")).toBeTruthy();
  });

  it("shows request status and lets a pending request be withdrawn", async () => {
    const mine = { ...claim, coded_identity: SAM };
    const calls = mockApi({
      ...employee,
      "GET /api/me/workflow": { body: { requests: [mine, { ...cert, coded_identity: SAM, status: "approved", decision_note: "thanks" }], goal: null } },
      [`POST /api/me/requests/${mine.request_id}/withdraw`]: { body: { ...mine, status: "withdrawn" } },
    });
    renderApp("/growth");
    const rows = await screen.findAllByTestId("my-request");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("Waiting for your manager")).toBeTruthy();
    expect(within(rows[1]).getByText("Approved")).toBeTruthy();
    expect(within(rows[1]).getByText(/thanks/)).toBeTruthy();
    fireEvent.click(within(rows[0]).getByRole("button", { name: "Withdraw" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/withdraw"))).toBe(true));
  });

  it("is closed to managers", async () => {
    mockApi({ "GET /api/session": { body: MANAGER_SESSION } });
    renderApp("/growth");
    expect(await screen.findByText("Not available for your role")).toBeTruthy();
  });
});

describe("Role lab", () => {
  const preview = {
    request_id: "role-lab",
    scoring_config_version: "x",
    computed_at: "2026-10-05T10:00:00Z",
    computation_run_id: "r",
    excluded_candidates: [{ coded_identity: "EMP-9a4bf2f6", reason: "missing_critical_skill" }],
    candidates: contract.request_detail.result.candidates,
  };

  it("previews live, saves nothing until asked, and saves a named role", async () => {
    const calls = mockApi({
      ...manager,
      "POST /api/fitness/preview": { body: preview },
      "POST /api/roles/custom": { body: { role_id: "custom_0123456789", role_name: "Platform Hero", required_skills: {}, critical_skills: [], min_coverage_ratio: 0.6 } },
    });
    renderApp("/role-lab");
    expect(await screen.findByRole("heading", { level: 1, name: "Role lab" })).toBeTruthy();
    expect(await screen.findByRole("list", { name: "Preview shortlist" })).toBeTruthy();
    expect(screen.getByText(/1 person is left out/)).toBeTruthy();
    expect(calls.every((c) => c.method === "GET" || c.path === "/api/fitness/preview")).toBe(true);

    const before = calls.filter((c) => c.path === "/api/fitness/preview").length;
    fireEvent.change(screen.getByLabelText("Level for Azure Networking"), { target: { value: "2" } });
    await waitFor(() => expect(calls.filter((c) => c.path === "/api/fitness/preview").length).toBeGreaterThan(before));
    const last = [...calls].reverse().find((c) => c.path === "/api/fitness/preview");
    expect((last?.body as { required_skills: Record<string, number> }).required_skills.azure_networking).toBe(2);

    fireEvent.change(screen.getByLabelText("Name for this role"), { target: { value: "Platform Hero" } });
    fireEvent.click(screen.getByRole("button", { name: "Save as a role" }));
    await waitFor(() => expect(calls.some((c) => c.path === "/api/roles/custom")).toBe(true));
    const saved = calls.find((c) => c.path === "/api/roles/custom")?.body as { role_name: string; required_skills: Record<string, number> };
    expect(saved.role_name).toBe("Platform Hero");
    expect(saved.required_skills.azure_networking).toBe(2);
  });
});

describe("Compare", () => {
  it("puts the shortlist side by side and exposes the picker", async () => {
    mockApi({ ...manager, [`GET /api/staffing/requests/${contract.request_detail.request_id}`]: { body: contract.request_detail } });
    renderApp(`/requests/${contract.request_detail.request_id}/compare`);
    expect(await screen.findByRole("heading", { level: 1, name: "Compare" })).toBeTruthy();
    expect(await screen.findByRole("table", { name: "Skill by skill comparison" })).toBeTruthy();
    // The fixture role lists two skills: too few for a radar, so it says so instead of drawing a flat line.
    expect(screen.getByText(/at least three skills/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Download CSV/ })).toBeTruthy();
  });

  it("draws the radar once the role lists three or more skills", async () => {
    const wide = {
      ...contract.request_detail,
      requirements: { ...contract.request_detail.requirements, required_skills: { azure_networking: 2, container_orchestration: 3, infrastructure_as_code: 3 } },
    };
    mockApi({ ...manager, [`GET /api/staffing/requests/${wide.request_id}`]: { body: wide } });
    renderApp(`/requests/${wide.request_id}/compare`);
    expect(await screen.findByRole("img", { name: /Skill levels by person/ })).toBeTruthy();
  });
});
