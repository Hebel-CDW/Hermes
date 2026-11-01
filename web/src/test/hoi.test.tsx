import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { contract, mockApi, renderApp } from "./harness";

const session = (sub: string, role: string) => ({ sub, roles: [role], coded_identity: null, data_classification: "synthetic" });
const SALES = session("demo-sales", "sales");
const MANAGER = { ...contract.session_manager, sub: "demo-manager" };
const FINANCE = session("demo-finance", "finance");

const OPP = {
  opportunity_id: "OPP-2026-ABC123", owner: "demo-sales", client_alias: "Northstar", name: "Cloud Modernisation", stage: "intake", status: "open",
  bid_deadline: null, geography: "Remote", currency: "USD", contract_type: "time_and_materials", duration_months: 6, start_date: null, end_date: null,
  is_synthetic: true, members: [], readiness: { documents: 1, requirements_status: "draft", has_approved_requirements: false, scenarios: 0, approved_scenarios: 0 },
};
const src = { document_id: "doc-1", start: 0, end: 5, quote: "Monitoring" };
const ROLE = {
  requirement_id: "rr-1", role_name: "Senior Cloud Engineer", headcount: 2, fte: "1", location: null, start_date: null, end_date: null, constraints: {}, origin: "extracted",
  skills: [{ text: "Monitoring", skill_id: "monitoring", skill_name: "Monitoring", level: null, criticality: "must", taxonomy_status: "mapped", source: src, confidence: 0.9, origin: "extracted", dismissed: false }],
};
const VERSION = (status: string, problems: string[]) => ({
  version_id: "rv-1", version_no: 1, status, parser_version: "hoi-rules-1.0", extraction_method: "rules", created_by: "demo-sales", approved_by: null, approved_at: null,
  content_hash: null, notes: [], source_doc_ids: ["doc-1"], roles: [ROLE], blocking_problems: problems,
});
const base = {
  "GET /api/opportunities": { body: { opportunities: [OPP] } },
  "GET /api/opportunities/OPP-2026-ABC123/documents": { body: { documents: [] } },
  "GET /api/hoi/status": { body: { module: "HOI", calc_version: "hoi-calc-1.0", implemented: ["opportunities"], pending_integrations: { malware_scanning: "none configured", hris_payroll: "not connected" }, limits: { max_upload_mb: 10, formats: [".pdf", ".docx", ".txt"] } } },
  "GET /api/hoi/skills": { body: { skills: [{ skill_id: "monitoring", name: "Monitoring" }, { skill_id: "python", name: "Python" }] } },
};

describe("Opportunity Intelligence UI", () => {
  it("shows a sales user only the deal pages and labels synthetic data", async () => {
    mockApi({ "GET /api/session": { body: SALES }, ...base });
    renderApp("/");
    expect(await screen.findByRole("heading", { level: 1, name: "RFP/SOW Workspace" })).toBeTruthy();
    const nav = within(screen.getByRole("complementary", { name: "Primary" })).getAllByRole("link").map((a) => a.textContent);
    expect(nav).toEqual(["RFP/SOW Workspace", "Market Intelligence", "Scenario Optimizer", "Architecture & Workflow", "Decisions & Audit"]);
    expect(await screen.findByText(/Synthetic demo data/)).toBeTruthy();
  });

  it("deal-team roles never request manager-only endpoints (no 403 noise)", async () => {
    const calls = mockApi({ "GET /api/session": { body: SALES }, ...base, "GET /api/opportunities/OPP-2026-ABC123/scenarios": { body: { scenarios: [] } } });
    renderApp("/scenarios");
    await screen.findByRole("heading", { level: 1, name: "Scenario Optimizer" });
    await screen.findByText("No scenarios yet");
    const paths = calls.map((c) => c.path);
    expect(paths).not.toContain("/api/skills");
    expect(paths).not.toContain("/api/identity/directory");
    expect(paths.some((p) => p.startsWith("/api/finance/"))).toBe(false);
    expect(paths).not.toContain("/api/rate-cards");
  });

  it("executive overview shows the opportunity pipeline from the API, and stays quiet if that call fails", async () => {
    const common = { "GET /api/session": { body: MANAGER }, "GET /api/overview": { body: contract.overview }, "GET /api/data-quality": { body: contract.data_quality } };
    mockApi({ ...common, "GET /api/opportunities": { body: { opportunities: [OPP] } } });
    const first = renderApp("/overview");
    const panel = await screen.findByRole("region", { name: "Opportunity pipeline" });
    expect(within(panel).getByText("OPP-2026-ABC123")).toBeTruthy();
    expect(within(panel).getByText("Northstar")).toBeTruthy();
    expect(within(panel).getByText("1")).toBeTruthy(); // readiness.documents, straight from the API
    expect(within(panel).getByText(/0 \(0 approved\)/)).toBeTruthy();
    first.unmount();
    mockApi({ ...common, "GET /api/opportunities": { status: 500, body: { detail: "boom" } } });
    renderApp("/overview");
    expect(await screen.findByRole("heading", { level: 1, name: "Executive Overview" })).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("status", { name: /Loading/ })).toBeNull());
    expect(screen.queryByRole("region", { name: "Opportunity pipeline" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("scenario warnings are written in plain language, naming the role", async () => {
    mockApi({
      "GET /api/session": { body: MANAGER }, ...base,
      "GET /api/opportunities/OPP-2026-ABC123/scenarios": { body: { scenarios: [SCEN({ calculable: false, economics: undefined,
        unresolved_constraints: ["headcount_unfilled:rr-1:2"], unresolved_detail: [{ code: "headcount_unfilled:rr-1:2", message: "Senior Cloud Engineer: 2 approved position(s) have nobody assigned yet" }] })] } },
      "GET /api/finance/cost-policies": { body: { policies: [] } }, "GET /api/rate-cards": { body: { rate_cards: [] } },
      "GET /api/overview": { body: contract.overview },
    });
    renderApp("/scenarios");
    expect(await screen.findByText(/Senior Cloud Engineer: 2 approved position/)).toBeTruthy();
    expect(screen.queryByText(/rr-1/)).toBeNull(); // no raw requirement id on screen
  });

  it("guards deal pages for employees", async () => {
    mockApi({ "GET /api/session": { body: contract.session_employee } });
    renderApp("/rfp");
    expect(await screen.findByText("Not available for your role")).toBeTruthy();
  });

  it("empty and error states", async () => {
    mockApi({ "GET /api/session": { body: SALES }, "GET /api/opportunities": { body: { opportunities: [] } } });
    renderApp("/rfp");
    expect(await screen.findByText("No opportunity yet")).toBeTruthy();
  });

  it("surfaces a permission error from the server instead of an empty page", async () => {
    mockApi({ "GET /api/session": { body: SALES }, "GET /api/opportunities": { status: 403, body: { detail: "role not permitted", error: "forbidden" } } });
    renderApp("/rfp");
    expect(await screen.findByText("Not authorized")).toBeTruthy();
  });

  it("requirement approval is blocked until a person supplies the missing level", async () => {
    const calls = mockApi({
      "GET /api/session": { body: SALES }, ...base,
      "GET /api/opportunities/OPP-2026-ABC123/requirements": { body: { versions: [], current: VERSION("draft", ["role[1]:skill_level_unknown:monitoring"]) } },
      "PUT /api/opportunities/OPP-2026-ABC123/requirements/rv-1": { body: { versions: [], current: VERSION("draft", []) } },
      "POST /api/opportunities/OPP-2026-ABC123/requirements/approve": { body: { versions: [], current: { ...VERSION("approved", []), approved_by: "demo-sales", content_hash: "a".repeat(64) } } },
    });
    renderApp("/rfp");
    fireEvent.click(await screen.findByRole("tab", { name: /Validate requirements/ }));
    const approve = (await screen.findByRole("button", { name: "Approve requirements" })) as HTMLButtonElement;
    expect(approve.disabled).toBe(true);
    expect(screen.getByRole("alert").textContent).toMatch(/skill level unknown/);
    expect(screen.getByText(/“Monitoring”/)).toBeTruthy(); // source quote shown
    expect((screen.getByLabelText("Headcount") as HTMLInputElement).value).toBe("2");
    expect((screen.getByLabelText("Taxonomy for Monitoring") as HTMLSelectElement).value).toBe("monitoring"); // mapped skill is shown as mapped
    fireEvent.change(screen.getByLabelText("Level for Monitoring"), { target: { value: "3" } });
    await waitFor(() => expect((screen.getByRole("button", { name: "Approve requirements" }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Approve requirements" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path.endsWith("/requirements/approve"))).toBe(true));
    const put = calls.find((c) => c.method === "PUT");
    expect((put!.body as { roles: { skills: { level: number }[] }[] }).roles[0].skills[0].level).toBe(3);
    expect(calls.findIndex((c) => c.method === "PUT")).toBeLessThan(calls.findIndex((c) => c.path.endsWith("/approve")));
  });

  const SHORT = (full: boolean) => ({
    match_run_id: "mr-1", requirement_version_id: "rv-1", redacted: !full,
    requirements: [{
      requirement_id: "rr-1", role_name: "Senior Cloud Engineer", headcount: 2, fte: "1", eligible_count: 1, candidate_count: 2,
      ...(full ? { staffing_request_id: "hoi-mr-1-1", candidates: [
        { coded_identity: "EMP-aaaa1111", rank: 1, fitness_score: 0.91, eligibility: "eligible", checks: [{ check: "capacity", status: "pass", detail: "available 1.00 FTE >= required 1.00" }], available_fte: 1, evidence_ids: ["INC-1"], explanation: { monitoring: "level 4 meets 3" }, fitness_run_id: "r" },
        { coded_identity: "EMP-bbbb2222", rank: 2, fitness_score: 0.7, eligibility: "ineligible", checks: [{ check: "capacity", status: "fail", detail: "available 0.00 FTE < required 1.00" }], available_fte: 0, evidence_ids: [], explanation: {}, fitness_run_id: "r" },
      ] } : {}),
    }],
  });

  it("manager sees coded candidates and reveals names only through the gateway", async () => {
    const calls = mockApi({
      "GET /api/session": { body: MANAGER }, ...base,
      "GET /api/opportunities/OPP-2026-ABC123/shortlist": { body: SHORT(true) },
      "POST /api/identity/resolve": { body: { resolved: [{ coded_identity: "EMP-aaaa1111", display_name: "Alex Rivera", rank: "1", fitness_score: "0.91" }] } },
      "GET /api/overview": { body: contract.overview },
    });
    renderApp("/rfp");
    fireEvent.click(await screen.findByRole("tab", { name: /Internal matches/ }));
    expect(await screen.findByText("EMP-aaaa1111")).toBeTruthy();
    expect(screen.getByText("ineligible")).toBeTruthy();
    expect(screen.queryByText("Alex Rivera")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Reveal names/ }));
    expect(await screen.findByText(/Alex Rivera/)).toBeTruthy();
    expect(calls.find((c) => c.path === "/api/identity/resolve")?.body).toEqual({ request_id: "hoi-mr-1-1" });
  });

  it("sales sees the redacted shortlist with no candidates", async () => {
    mockApi({ "GET /api/session": { body: SALES }, ...base, "GET /api/opportunities/OPP-2026-ABC123/shortlist": { body: SHORT(false) } });
    renderApp("/rfp");
    fireEvent.click(await screen.findByRole("tab", { name: /Internal matches/ }));
    expect(await screen.findByText(/visible to the delivery manager only/)).toBeTruthy();
    expect(screen.queryByText(/EMP-/)).toBeNull();
    expect(screen.queryByRole("button", { name: /Run internal match/ })).toBeNull();
  });

  const SCEN = (over = {}) => ({
    scenario_id: "sc-1", opportunity_id: OPP.opportunity_id, kind: "internal", status: "draft", version_no: 1, requirement_version_id: "rv-1", currency: "USD", months: 6,
    calc_version: "hoi-calc-1.0", input_hash: "f".repeat(64), calculable: true, auto_generated: true, override_required: false, unresolved_constraints: [],
    approvals: { required: ["delivery", "finance"], latest: {}, pending: ["delivery", "finance"], complete: false, rejected: false }, no_automatic_assignment: true,
    assignments: [{ requirement_id: "rr-1", resource_type: "internal", coded_identity: "EMP-aaaa1111", fte: "1", fitness_rank: 1, cost_basis: "role_band_loaded_cost" }],
    risk: { level: "low", flags: [], basis: "rule-based; not a probability" }, lead_time_weeks: { internal_weeks: 2, external_weeks: null, overall_weeks: 2 }, capacity: [],
    uses_individual_cost: false, economics: { revenue: "78000.00", margin_band: "30-40%", currency: "USD" }, ...over,
  });

  it("delivery manager sees a margin band and no cost figures; override reason is demanded", async () => {
    const calls = mockApi({
      "GET /api/session": { body: MANAGER }, ...base,
      "GET /api/opportunities/OPP-2026-ABC123/scenarios": { body: { scenarios: [SCEN({ override_required: true })] } },
      "GET /api/finance/cost-policies": { body: { policies: [{ parameter_id: "p", kind: "policy", name: "POL-2026", version: 1, status: "approved", created_by: "demo-finance" }] } },
      "GET /api/rate-cards": { body: { rate_cards: [{ parameter_id: "r", kind: "rate_card", name: "RATE-01", version: 1, status: "approved", created_by: "demo-finance" }] } },
      "POST /api/opportunities/OPP-2026-ABC123/approvals": { body: SCEN({ status: "partially_approved" }) },
      "GET /api/overview": { body: contract.overview },
    });
    renderApp("/scenarios");
    expect(await screen.findByText(/margin 30-40%/)).toBeTruthy();
    expect(screen.queryByText(/Delivery cost/)).toBeNull();
    expect(screen.getByText(/override reason needed/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open details" }));
    expect(await screen.findByText(/does not assign anyone/)).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Override reason/), { target: { value: "customer request" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve as delivery" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/approvals"))).toBe(true));
    expect(calls.find((c) => c.path.endsWith("/approvals"))!.body).toMatchObject({ approver_role: "delivery", outcome: "approved", override_reason: "customer request" });
  });

  it("finance sees full economics from the server and an unresolved scenario states what is missing", async () => {
    mockApi({
      "GET /api/session": { body: FINANCE }, ...base,
      "GET /api/finance/summary": { body: { loaded_cost_rows: { role_band: 2 }, policies: 1, rate_cards: 1 } },
      "GET /api/opportunities/OPP-2026-ABC123/scenarios": { body: { scenarios: [
        SCEN({ economics: { revenue: "72000.00", currency: "USD", delivery_cost: "48000.00", cogs: "48000.00", gross_profit: "24000.00", gross_margin_pct: "33.33", contribution: "24000.00", contribution_margin_pct: "33.33", breakdown: { direct_labor_internal: "42000.00", project_direct_costs: "6000.00" } } }),
        SCEN({ scenario_id: "sc-2", kind: "external", calculable: false, economics: undefined, unresolved_constraints: ["market_benchmark_missing:rr-1"] }),
      ] } },
      "GET /api/finance/cost-policies": { body: { policies: [] } }, "GET /api/rate-cards": { body: { rate_cards: [] } },
    });
    renderApp("/commercial");
    const card = await screen.findByRole("region", { name: "Economics internal v1" });
    expect(within(card).getByText("48000.00")).toBeTruthy();
    expect(within(card).getAllByText("24000.00").length).toBeGreaterThan(0);
    expect(within(card).getByText(/gross margin 33.33%/)).toBeTruthy();
    const bad = screen.getByRole("region", { name: "Economics external v1" });
    expect(within(bad).getByText(/No figure is estimated/)).toBeTruthy();
    expect(screen.getByText(/Values are never shown here/)).toBeTruthy();
  });

  it("market page labels synthetic rows and requires provenance before import", async () => {
    mockApi({
      "GET /api/session": { body: FINANCE }, ...base,
      "GET /api/market/benchmarks": { body: { synthetic_rows: 1, note: "n", benchmarks: [{ benchmark_id: "b1", role: "Senior Cloud Engineer", geography: "Remote", seniority: "senior", engagement_type: "contractor", basis: "contractor_cost", currency: "USD", unit: "month", p25: "9800", p50: "11200", p75: "12900", sample_count: 3, source: "SYNTHETIC demo dataset", as_of: "2026-09-30", time_to_fill_weeks: 6, is_synthetic: true, coverage: "synthetic" }] } },
    });
    renderApp("/market");
    expect((await screen.findAllByText(/Contractor cost/)).length).toBeGreaterThan(0);
    expect(screen.getAllByText("synthetic").length).toBeGreaterThan(0);
    expect(screen.getByText(/There is no live salary, ATS or vendor feed/)).toBeTruthy();
    expect((screen.getByRole("button", { name: /Import \(all-or-nothing\)/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByLabelText(/Synthetic \/ illustrative/));
    expect((screen.getByRole("button", { name: /Import \(all-or-nothing\)/ }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("architecture page states pending integrations honestly", async () => {
    mockApi({ "GET /api/session": { body: MANAGER }, ...base, "GET /api/overview": { body: contract.overview } });
    renderApp("/architecture");
    expect(await screen.findByText(/Pending — needs enterprise access, not simulated/)).toBeTruthy();
    expect(screen.getByText(/hris payroll/)).toBeTruthy();
  });

  it("audit page shows chain validity", async () => {
    mockApi({
      "GET /api/session": { body: SALES }, ...base,
      "GET /api/opportunities/OPP-2026-ABC123/audit": { body: { opportunity_id: OPP.opportunity_id, chain_valid: false, head_hash: "e".repeat(64), events: [{ seq: 1, event_type: "opportunity_created", actor: "demo-sales", object: "OPP", version: "", evidence_hash: "", detail: { client_alias: "Northstar" }, created_at: "2026-10-31T10:00:00Z", row_hash: "x" }] } },
    });
    renderApp("/decisions");
    expect(await screen.findByText("BROKEN")).toBeTruthy();
    expect(screen.getByText("opportunity created")).toBeTruthy();
  });
});
