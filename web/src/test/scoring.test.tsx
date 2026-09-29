import { fireEvent, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { RequestDetail } from "../api/types";
import { contract, fixed4, MANAGER_SESSION, mockApi, renderApp } from "./harness";

const detail = contract.request_detail as unknown as RequestDetail;
const ID = detail.request_id;
const [first, second] = detail.result.candidates;
const url = (coded: string, derivation = false) => `/capability/${coded}?request=${ID}${derivation ? "&view=derivation" : ""}`;
const base = {
  "GET /api/session": { body: MANAGER_SESSION },
  [`GET /api/staffing/requests/${ID}`]: { body: detail },
  "POST /api/identity/resolve": { body: { resolved: [] } },
};

describe("candidate detail and score derivation (real API contract payloads)", () => {
  it("candidate detail shows the stored candidate id and fitness", async () => {
    mockApi(base);
    renderApp(url(first.coded_identity));
    expect((await screen.findByTestId("candidate-id")).textContent).toBe(first.coded_identity);
    expect(screen.getByTestId("fitness").textContent).toBe(fixed4(first.fitness_score));
    expect(screen.getAllByTestId("delta-row")).toHaveLength(Object.keys(first.reasoning_detail).length);
  });

  it("on synthetic data, candidate detail titles with the resolved display name", async () => {
    mockApi({
      ...base,
      "POST /api/identity/resolve": {
        body: { resolved: [{ coded_identity: first.coded_identity, display_name: "Alex Rivera", rank: "1", fitness_score: "0.0" }] },
      },
    });
    renderApp(url(first.coded_identity));
    expect((await screen.findByTestId("resolved-name")).textContent).toBe("Alex Rivera");
    expect(screen.getByTestId("candidate-id").textContent).toBe(first.coded_identity);
  });

  it("score derivation renders every backend operand exactly", async () => {
    mockApi(base);
    renderApp(url(first.coded_identity, true));
    const calc = first.calculation!;
    expect((await screen.findByTestId("derivation-fitness")).textContent).toBe(fixed4(calc.fitness_score));
    expect(screen.getByTestId("run-id").textContent).toBe(calc.computation_run_id);
    expect(screen.getByTestId("config-version").textContent).toBe(calc.scoring_config_version);
    expect(calc.scoring_config_version).toBe(detail.result.scoring_config_version);
    for (const s of Object.values(first.reasoning_detail)) {
      expect(screen.getByTestId(`ledger-${s.skill_id}`)).toBeTruthy();
      const contribution = screen.getByTestId(`contribution-${s.skill_id}`);
      expect(contribution.getAttribute("data-value")).toBe(s.contribution === null ? "" : String(s.contribution));
      expect(contribution.textContent).toBe(s.contribution === null ? "0 (missing)" : s.contribution.toFixed(6));
      const shown = (v: number | null) => (v === null ? "—" : fixed4(v));
      expect(screen.getByTestId(`confidence-${s.skill_id}`).textContent).toBe(shown(s.confidence));
      expect(screen.getByTestId(`volume-${s.skill_id}`).textContent).toBe(shown(s.volume_score));
      expect(screen.getByTestId(`freshness-${s.skill_id}`).textContent).toBe(shown(s.freshness));
      expect(screen.getByTestId(`adjacency-${s.skill_id}`).textContent).toBe(fixed4(s.adjacency_discount));
    }
    const formula = screen.getByTestId("formula-substituted").textContent!;
    expect(formula).toContain(`= ${calc.mean_contribution}`);
    expect(formula).toContain(`${calc.allocation_multiplier} = ${calc.fitness_score}`);
    expect(screen.getByText(calc.formula)).toBeTruthy();
  });

  it("shows the API exclusion reason for an excluded candidate", async () => {
    const excluded = detail.result.excluded_candidates[0];
    mockApi(base);
    renderApp(url(excluded.coded_identity));
    const panel = await screen.findByTestId("candidate-excluded");
    expect(panel.textContent).toContain(excluded.reason);
    expect(screen.queryByTestId("fitness")).toBeNull();
  });

  it("requires a request context", async () => {
    mockApi(base);
    renderApp(`/capability/${first.coded_identity}`);
    expect(await screen.findByText("Open a candidate from a ranked request")).toBeTruthy();
  });

  it("switching candidates never shows the previous candidate's values", async () => {
    let n = 0;
    mockApi({
      ...base,
      // The first load is slow; the navigation to the next candidate must not be overwritten by it.
      [`GET /api/staffing/requests/${ID}`]: () => ({ body: detail, delay: n++ === 0 ? 150 : 0 }),
    });
    renderApp(url(first.coded_identity, true));
    await screen.findByTestId("derivation-fitness");
    fireEvent.click(screen.getByRole("link", { name: "Next candidate" }));
    await waitFor(() => expect(screen.getByTestId("candidate-id").textContent).toBe(second.coded_identity));
    await new Promise((r) => setTimeout(r, 200));
    expect(screen.getByTestId("candidate-id").textContent).toBe(second.coded_identity);
    expect(screen.getByTestId("derivation-fitness").textContent).toBe(fixed4(second.calculation!.fitness_score));
  });
});
