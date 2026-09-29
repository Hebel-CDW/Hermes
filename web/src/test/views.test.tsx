import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { contract, DIRECTORY, EMPLOYEE_SESSION, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const staff = { "GET /api/session": { body: MANAGER_SESSION }, "GET /api/data-quality": { body: contract.data_quality } };

describe("read views (real API contract payloads)", () => {
  it("overview renders API counts, domains and provenance", async () => {
    mockApi({ ...staff, "GET /api/overview": { body: contract.overview } });
    renderApp("/overview");
    const kpis = await screen.findByRole("region", { name: "Key figures" });
    const kpi = (label: string) => within(kpis).getByText(label).parentElement!.querySelector(".kpi-value")!.textContent;
    expect(kpi("People")).toBe(String(contract.overview.people));
    expect(kpi("Skills tracked")).toBe(String(contract.overview.governed_skills));
    expect(kpi("People with proven skills")).toBe(`${contract.overview.demonstrated_coverage.coverage_pct.toFixed(1)}%`);
    expect(kpi("Open requests")).toBe(String(contract.overview.requests_by_status.open ?? 0));
    for (const d of contract.overview.domains) expect(screen.getByText(d.name)).toBeTruthy();
    expect(screen.getByText(contract.overview.scoring_config_version)).toBeTruthy();
    expect(within(screen.getByRole("complementary", { name: "Primary" })).getByRole("link", { name: "Update skills" })).toBeTruthy();
  });

  it("overview shows an empty state when there is no workforce", async () => {
    mockApi({ ...staff, "GET /api/overview": { body: { ...contract.overview, people: 0 } } });
    renderApp("/overview");
    expect(await screen.findByText("No workforce data yet")).toBeTruthy();
  });

  it.each([
    [500, "Server error"],
    [503, "Service unavailable"],
    [404, "Not found"],
  ])("renders %i as a human error state", async (status, title) => {
    mockApi({ ...staff, "GET /api/overview": { status, body: { detail: "boom" } } });
    renderApp("/overview");
    expect(await screen.findByText(title)).toBeTruthy();
  });

  it("shows a loading state while data is in flight", async () => {
    mockApi({ ...staff, "GET /api/overview": { body: contract.overview, delay: 100 } });
    renderApp("/overview");
    expect(await screen.findByRole("status", { name: "Loading overview" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("status", { name: "Loading overview" })).toBeNull());
  });

  it("workforce selects a coded identity and shows its API skills", async () => {
    mockApi({ ...staff, "GET /api/workforce": { body: contract.workforce } });
    renderApp("/workforce");
    const target = contract.workforce.identities.find((i) => i.skill_count > 0 && i !== contract.workforce.identities[0])!;
    fireEvent.click(await screen.findByRole("button", { name: `${target.coded_identity}, ${target.skill_count} skills` }));
    expect(screen.getByTestId("selected-identity").textContent).toBe(target.coded_identity);
    for (const s of target.skills) expect(screen.getAllByText(s.skill_name).length).toBeGreaterThan(0);
  });

  it("skills atlas uses the ontology and the skill summary endpoint", async () => {
    mockApi({ ...staff, "GET /api/skills": { body: contract.skills }, "GET /api/skills/container_orchestration": { body: contract.skill_detail } });
    renderApp("/skills");
    expect((await screen.findByTestId("skill-name")).textContent).toBe(contract.skill_detail.name);
    for (const s of contract.skills.skills) expect(screen.getAllByText(s.name).length).toBeGreaterThan(0);
  });

    it("matrix cells show API levels and empty cells have no level", async () => {
    mockApi({ ...staff, "GET /api/dashboard": { body: contract.dashboard }, "GET /api/skills": { body: contract.skills }, "GET /api/workforce": { body: contract.workforce } });
    renderApp("/matrix");
    await screen.findByRole("table", { name: "Skill matrix" });
    const present = new Set(contract.dashboard.skill_distribution.map((r) => `${r.skill_id}-${r.coded_identity}`));
    for (const r of contract.dashboard.skill_distribution) {
      const cell = screen.getByTestId(`cell-${r.skill_id}-${r.coded_identity}`);
      expect(cell.className).toContain(`l${r.proficiency}`);
      expect(cell.textContent).toBe(String(r.proficiency));
    }
    for (const s of contract.skills.skills) {
      for (const i of contract.workforce.identities) {
        if (!present.has(`${s.skill_id}-${i.coded_identity}`)) expect(screen.getByTestId(`cell-${s.skill_id}-${i.coded_identity}`).className).toContain("l0");
      }
    }
  });

  it("matrix survey toggle labels the 2025 workbook as not used for Find people", async () => {
    const person = contract.dashboard.skill_distribution[0];
    mockApi({
      ...staff,
      "GET /api/dashboard": { body: contract.dashboard },
      "GET /api/skills": { body: contract.skills },
      "GET /api/workforce": { body: contract.workforce },
      "GET /api/baseline/matrix": {
        body: {
          kind: "survey_2025",
          used_for_fitness: false,
          label: "2025 manager survey — not used for Find people",
          cells: [{ coded_identity: person.coded_identity, skill_id: person.skill_id, raw_label: "Kubernetes", level: 4, source_sheet: "Azure" }],
        },
      },
    });
    renderApp("/matrix");
    fireEvent.click(await screen.findByTestId("matrix-mode-survey"));
    expect(await screen.findByTestId("survey-disclaimer")).toBeTruthy();
    expect(screen.getByRole("table", { name: "2025 survey matrix" })).toBeTruthy();
    expect(screen.getAllByText(/not used for Find people/i).length).toBeGreaterThan(0);
  });

  it("data quality taxonomy inbox lists pending aliases", async () => {
    mockApi({
      ...staff,
      "GET /api/taxonomy/pending": {
        body: { pending: [{ alias_label: "k8s admin", skill_id: "", mapped_by: "pending", proposed_skill_id: "container_orchestration" }] },
      },
    });
    renderApp("/data-quality");
    expect(await screen.findByTestId("taxonomy-inbox")).toBeTruthy();
    expect(await screen.findByText(/k8s admin/)).toBeTruthy();
    expect(screen.getByText(/container_orchestration/)).toBeTruthy();
  });

  it("overview kill gate says the next workbook is frozen", async () => {
    mockApi({
      ...staff,
      "GET /api/overview": { body: contract.overview },
      "GET /api/excel-sunset": {
        body: {
          survey_year_frozen: 2025,
          next_workbook_year_forbidden: 2026,
          next_workbook_allowed: false,
          ready_to_retire_excel: false,
          criteria: {
            survey_frozen: true,
            pilot_coverage_pct: 0,
            pilot_coverage_met: false,
            baseline_agreement_overlaps: 0,
            baseline_agreement_met: false,
            staffing_decisions: 0,
            staffing_decision_met: false,
          },
        },
      },
    });
    renderApp("/overview");
    const dual = await screen.findByRole("region", { name: "Survey versus living" });
    expect(within(dual).getByText("Frozen")).toBeTruthy();
  });

  it("profile reads /api/me with no identity parameter and shows the server identity", async () => {
    const calls = mockApi({ "GET /api/session": { body: EMPLOYEE_SESSION }, "GET /api/me": { body: contract.me_employee }, "GET /api/skills": { body: contract.skills } });
    renderApp("/profile?coded_identity=EMP-00000000");
    await screen.findAllByTestId("me-skill");
    expect(calls.filter((c) => c.path.startsWith("/api/me")).map((c) => c.path)).toEqual(["/api/me"]);
    expect(screen.getByTestId("session-coded").textContent).toBe(contract.session_employee.coded_identity);
    expect(screen.getAllByTestId("me-skill")).toHaveLength(contract.me_employee.skills.length);
  });

  it("learning shows engine gaps and no invented courses", async () => {
    const gaps = { coded_identity: EMPLOYEE_SESSION.coded_identity, role_id: "r", scoring_config_version: "v", gaps: [{ skill_id: "azure_networking", required_level: 4, current_level: null, demand_impact: 1, reasoning: "engine text", evidence_ids: [] }] };
    const calls = mockApi({ "GET /api/session": { body: EMPLOYEE_SESSION }, "GET /api/roles": { body: contract.roles }, "POST /api/fitness/gaps": { body: gaps } });
    renderApp("/learning");
    fireEvent.click(await screen.findByRole("button", { name: "See what they should learn" }));
    expect(await screen.findByText("engine text")).toBeTruthy();
    expect(screen.getByText("No learning catalogue connected")).toBeTruthy();
    expect(calls.some((c) => c.path === "/api/identities")).toBe(false);
    expect((calls.find((c) => c.path === "/api/fitness/gaps")?.body as { coded_identity: string }).coded_identity).toBe(EMPLOYEE_SESSION.coded_identity);
  });

  it("matrix headers show synthetic directory names", async () => {
    mockApi({
      ...staff,
      "GET /api/dashboard": { body: contract.dashboard },
      "GET /api/skills": { body: contract.skills },
      "GET /api/workforce": { body: contract.workforce },
      "GET /api/identity/directory": { body: DIRECTORY },
    });
    renderApp("/matrix");
    await screen.findByRole("table", { name: "Skill matrix" });
    expect(await screen.findByText("Alex Rivera")).toBeTruthy();
    expect(screen.getByText("EMP-fd8efec3")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Update skills" }).length).toBeGreaterThan(1);
    fireEvent.click(screen.getAllByRole("button", { name: /Alex Rivera: level/ })[0]);
    expect(screen.getByRole("link", { name: "Update this person" }).getAttribute("href")).toBe(
      "/update-skills?person=EMP-fd8efec3",
    );
  });

  it("learning person options show synthetic directory names", async () => {
    mockApi({
      ...staff,
      "GET /api/roles": { body: contract.roles },
      "GET /api/identities": { body: { identities: ["EMP-f232ab6e"] } },
      "GET /api/identity/directory": { body: DIRECTORY },
    });
    renderApp("/learning");
    const select = (await screen.findByRole("combobox", { name: "Person" })) as HTMLSelectElement;
    await waitFor(() => expect([...select.options].map((o) => o.textContent).join(" ")).toMatch(/Alex Rivera/));
    expect([...select.options].map((o) => o.textContent).join(" ")).toMatch(/Sam Patel/);
  });
});
