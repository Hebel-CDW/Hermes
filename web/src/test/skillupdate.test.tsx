import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { contract, DIRECTORY, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const SELF = MANAGER_SESSION.coded_identity!;
const REPORT = "EMP-c775791c";

const review = {
  coded_identity: SELF,
  matrix: [
    {
      skill_id: "container_orchestration",
      proficiency: 4,
      confidence: 1,
      freshness: 0.4,
      volume_score: 0.5,
      sources: ["demonstrated", "certified"],
    },
  ],
  contests: [
    {
      contest_id: "contest-1",
      coded_identity: SELF,
      skill_id: "incident_management",
      reason: "I ran the last sev1",
      status: "open",
      created_at: "2026-09-01T00:00:00Z",
    },
  ],
};

const staff = {
  "GET /api/session": { body: MANAGER_SESSION },
  "GET /api/skills": { body: contract.skills },
  "GET /api/identities": { body: { identities: [REPORT] } },
  "GET /api/identity/directory": { body: DIRECTORY },
  [`GET /api/team/skill-review/${SELF}`]: { body: review },
  [`GET /api/team/skill-review/${REPORT}`]: {
    body: { ...review, coded_identity: REPORT, contests: [] },
  },
  "POST /api/team/declare": { body: { status: "saved", coded_identity: REPORT, skill_id: "incident_management", evidence_id: "mgr-decl-1" } },
  "POST /api/team/contests/contest-1/resolve": { body: { contest_id: "contest-1", status: "confirmed" } },
};

describe("Update skills", () => {
  it("shows named people, not EMP headings, and posts coded identity + skill + level only", async () => {
    const calls = mockApi(staff);
    renderApp("/update-skills");
    expect(await screen.findByRole("heading", { level: 1, name: "Update skills" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: /EMP-/ })).toBeNull();
    const person = (await screen.findByRole("combobox", { name: "Person" })) as HTMLSelectElement;
    await waitFor(() => expect([...person.options].map((o) => o.textContent).join(" ")).toMatch(/Alex Rivera/));
    expect([...person.options].map((o) => o.textContent).join(" ")).toMatch(/Jordan Lee/);
    expect(screen.getByText(/You do not re-rate the whole team/)).toBeTruthy();

    fireEvent.change(person, { target: { value: REPORT } });
    await screen.findByRole("table", { name: "Known skills" });
    fireEvent.change(screen.getByRole("combobox", { name: "Skill" }), { target: { value: "incident_management" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Level" }), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Record this skill" }));
    await screen.findByText("Saved as your confirmation. Rankings will use it at declared weight.");
    const posted = calls.find((c) => c.path === "/api/team/declare");
    expect(posted?.body).toEqual({ coded_identity: REPORT, skill_id: "incident_management", proficiency: 3 });
  });

  it("confirms an open contest with the same declare path", async () => {
    const calls = mockApi(staff);
    renderApp("/update-skills");
    expect(await screen.findByTestId("contest-row")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(calls.some((c) => c.path === "/api/team/contests/contest-1/resolve" && (c.body as { status: string }).status === "confirmed")).toBe(true),
    );
  });
});
