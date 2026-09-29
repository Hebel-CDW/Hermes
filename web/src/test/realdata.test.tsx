import { fireEvent, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { DataQuality, Workforce } from "../api/types";
import { rejectionText } from "../lib/format";
import { contract, mockApi, renderApp } from "./harness";

/**
 * Real-data mode. Payloads were captured from the real-data ingestion path run on an
 * INVENTED workbook (scripts/export_ui_contract.py); numbers are asserted against the
 * payload, never hardcoded.
 */
const dq = contract.real_data_quality as unknown as DataQuality;
const workforce = contract.real_workforce as unknown as Workforce;
const real = {
  "GET /api/session": { body: contract.real_session_manager },
  "GET /api/data-quality": { body: dq },
  "GET /api/overview": { body: contract.real_overview },
  "GET /api/workforce": { body: workforce },
  "GET /api/dashboard": { body: contract.real_dashboard },
  "GET /api/skills": { body: contract.real_skills },
  "GET /api/skills/container_orchestration": { body: contract.skill_detail },
};

const n = (v: number | null | undefined) => (v ?? 0).toLocaleString("en-US");

describe("real workforce data (real-mode API payloads)", () => {
  it("labels the served database as real, from the server session", async () => {
    mockApi(real);
    renderApp("/data-quality");
    expect((await screen.findByTestId("data-classification")).textContent).toBe("Real workforce data");
    expect(screen.getByText("Real data · coded identities")).toBeTruthy();
  });

  it("data quality shows imported / validated / mapped / pending / scored exactly as the API", async () => {
    mockApi(real);
    renderApp("/data-quality");
    await screen.findByRole("region", { name: "Data pipeline states" });
    const stage = (id: string) => within(screen.getByTestId(`pipeline-${id}`)).getByText(/^[\d,—]+$/).textContent;
    expect(stage("imported")).toBe(n(dq.pipeline.imported));
    expect(stage("validated")).toBe(n(dq.pipeline.validated));
    expect(stage("mapped")).toBe(n(dq.pipeline.mapped));
    expect(stage("pending")).toBe(n(dq.pipeline.pending));
    expect(stage("scored")).toBe("0");
    const kpis = screen.getByRole("region", { name: "Ingestion figures" });
    const kpi = (label: string) => within(kpis).getByText(label).parentElement!.querySelector(".kpi-value")!.textContent;
    expect(kpi("People imported")).toBe(n(dq.database.people_imported));
    expect(kpi("Accepted cells")).toBe(n(dq.ingestion!.cells_accepted));
    expect(kpi("Rejected cells")).toBe(n(dq.ingestion!.cells_rejected));
    expect(kpi("Pending mappings")).toBe(n(dq.ingestion!.labels.pending));
    expect(kpi("Mapped skills")).toBe(n(dq.ingestion!.labels.mapped));
    expect(kpi("Certificates")).toBe(n(dq.certificates.staged));
  });

  it("shows every rejection category with its API count", async () => {
    mockApi(real);
    renderApp("/data-quality");
    const rows = within(await screen.findByTestId("rejections")).getAllByText(/./, { selector: ".ink-2" });
    const shown = Object.fromEntries(rows.map((r) => [r.textContent, r.parentElement!.querySelector(".count")!.textContent]));
    for (const [code, count] of Object.entries(dq.ingestion!.rejections_by_reason)) {
      expect(shown[rejectionText(code)]).toBe(n(count));
    }
  });

  it("shows certificates as exact / pending / dated / promoted from the API", async () => {
    mockApi(real);
    renderApp("/data-quality");
    const text = (await screen.findByTestId("certificates")).textContent!;
    expect(text).toContain(`Exact code match${n(dq.certificates.exact_mapped)}`);
    expect(text).toContain(`Pending mapping${n(dq.certificates.pending)}`);
    expect(text).toContain(`Earned date recorded${n(dq.certificates.with_earned_at)}`);
  });

  it("matrix shows the unavailable state with the API pending count instead of a fake grid", async () => {
    mockApi(real);
    renderApp("/matrix");
    expect(await screen.findByText("Real capability matrix unavailable")).toBeTruthy();
    expect(screen.getByText("Skill labels require governed mapping before scoring.")).toBeTruthy();
    expect(screen.getByTestId("matrix-pending").textContent).toBe(`${n(dq.pipeline.pending)} pending mappings`);
    expect(screen.queryByRole("table", { name: "Skill matrix" })).toBeNull();
  });

  it("workforce shows no scored capability for unscored identities and never a percentage", async () => {
    mockApi(real);
    renderApp("/workforce");
    expect(await screen.findByTestId("no-scored-capability")).toBeTruthy();
    expect(screen.getByTestId("unscored-count").textContent).toBe(`${n(workforce.identities.length)} coded identities`);
    const chip = screen.getAllByRole("button", { name: /^EMP-[0-9a-f]{8}$/ })[1];
    fireEvent.click(chip);
    expect(screen.getByTestId("selected-identity").textContent).toBe(chip.textContent);
    expect(screen.getByTestId("ledger-unscored")).toBeTruthy();
    expect(screen.queryByText("Mean confidence")).toBeNull();
  });

  it("skill atlas keeps canonical skills separate from pending workbook labels", async () => {
    mockApi(real);
    renderApp("/skills");
    const card = await screen.findByTestId("workbook-labels");
    expect(card.textContent).toContain(`${contract.real_skills.skills.length} canonical skills`);
    expect(card.textContent).toContain(`${n(dq.ingestion!.labels.pending)} pending mapping`);
    expect(screen.queryByText("terraform modules")).toBeNull();
  });

  it("overview shows the pipeline and no scored capability", async () => {
    mockApi(real);
    renderApp("/overview");
    expect(await screen.findByTestId("overview-unscored")).toBeTruthy();
    expect(within(screen.getByTestId("pipeline-scored")).getByText("0")).toBeTruthy();
  });

  it("profile does not call /api/me for a principal without a coded identity", async () => {
    const calls = mockApi(real);
    renderApp("/profile");
    expect(await screen.findByText("No personal skill profile")).toBeTruthy();
    expect(calls.some((c) => c.path === "/api/me")).toBe(false);
  });

  it("real-mode payloads rendered by the UI contain no names or client labels", () => {
    const text = JSON.stringify(contract).toLowerCase();
    for (const forbidden of ["zephyrine", "barnaby", "marigold", "percival", "example-client-alpha", "display_name"]) {
      expect(text).not.toContain(forbidden);
    }
  });
});
