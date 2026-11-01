import { useState } from "react";
import { hoiApi } from "../../api/endpoints";
import type { HoiScenario } from "../../api/types";
import { useApi, useStale } from "../../lib/useApi";
import { Kpi, PageHead } from "../../ui/Bits";
import { useToasts } from "../../ui/Fx";
import { EmptyState, ErrorState, InlineError, Loading } from "../../ui/States";
import { Chip, OppGate, OppPicker, SyntheticBanner, pretty, useRoles, useSelectedOpp } from "./common";

export default function Commercial() {
  const sel = useSelectedOpp();
  const { has } = useRoles();
  return (
    <>
      <PageHead
        trail={["Opportunity Intelligence", "Commercial Simulator"]}
        title="Commercial Simulator"
        lede="Revenue, delivery cost, gross profit and margin from approved Finance inputs. Every figure is calculated by the server; this page never computes money."
      />
      <div className="notice warn" role="note" style={{ marginBottom: 12 }}>
        Individual compensation lives in a separate, encrypted Finance store and is visible only to Finance. Delivery managers see revenue and a margin band;
        gross margin and contribution margin are reported separately.
      </div>
      {has("finance") && <FinancePanel />}
      <OppGate sel={sel}>
        {(opp) => (
          <>
            <div className="chip-row"><OppPicker opps={sel.opps} selected={sel.selected} select={sel.select} /></div>
            <SyntheticBanner show={opp.is_synthetic} />
            <Simulator oid={opp.opportunity_id} months={opp.duration_months} />
          </>
        )}
      </OppGate>
    </>
  );
}

function FinancePanel() {
  const sum = useApi((s) => hoiApi.financeSummary(s), []);
  const [pol, setPol] = useState({ name: "POL-2026", overhead_pct: "10", contingency_pct: "5", training_per_fte: "0", travel_per_fte_month: "0", tools_per_fte_month: "0", recruiting_onboarding_per_external_slot: "0", transition_total: "0", overhead_treatment: "below_gross", internal_lead_weeks: "" });
  const [card, setCard] = useState({ name: "RATE-01", currency: "USD", role: "", rate: "" });
  const [rates, setRates] = useState<Record<string, string>>({});
  const [cost, setCost] = useState({ scope: "role_band", subject: "", monthly_cost: "", currency: "USD", effective_from: "2026-01-01", source: "" });
  const [err, setErr] = useState<Error | null>(null);
  const { push, host } = useToasts();
  const attempt = async (fn: () => Promise<unknown>, ok: string) => {
    setErr(null);
    try { await fn(); push(ok, "ok"); sum.reload(); } catch (e) { setErr(e as Error); }
  };
  const savePolicy = () => {
    const { name, internal_lead_weeks, ...rest } = pol;
    return attempt(() => hoiApi.putPolicy(name, { ...rest, ...(internal_lead_weeks ? { internal_lead_weeks: Number(internal_lead_weeks) } : {}) }), "Cost policy saved as a new version");
  };
  return (
    <details className="panel" open style={{ marginBottom: 16 }}>
      <summary className="panel-head"><h2>Finance controls</h2></summary>
      {host}
      <div className="panel-body" style={{ display: "grid", gap: 16 }}>
        {sum.status === "success" && (
          <div className="muted">Stored: {Object.entries(sum.data.loaded_cost_rows).map(([k, v]) => `${v} ${pretty(k)}`).join(", ") || "no loaded costs"} · {sum.data.policies} policy versions · {sum.data.rate_cards} rate card versions. Values are never shown here.</div>
        )}
        <fieldset style={{ border: 0, padding: 0, display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))" }}>
          <legend className="label">Cost policy (percentages 0–100; money in scenario currency)</legend>
          {Object.entries(pol).map(([k, v]) => k === "overhead_treatment" ? (
            <label className="field compact" key={k}><span className="label">Overhead treatment</span>
              <select className="select" value={v} onChange={(e) => setPol({ ...pol, [k]: e.target.value })}><option value="below_gross">below gross margin</option><option value="in_cogs">inside COGS</option></select></label>
          ) : (
            <label className="field compact" key={k}><span className="label">{pretty(k)}</span><input className="input" value={v} onChange={(e) => setPol({ ...pol, [k]: e.target.value })} /></label>
          ))}
          <div style={{ alignSelf: "end" }}><button className="btn" onClick={savePolicy}>Save policy</button></div>
        </fieldset>
        <fieldset style={{ border: 0, padding: 0, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <legend className="label">Customer rate card (monthly bill rate per role)</legend>
          <label className="field compact"><span className="label">Name</span><input className="input" value={card.name} onChange={(e) => setCard({ ...card, name: e.target.value })} /></label>
          <label className="field compact"><span className="label">Currency</span><input className="input" maxLength={3} value={card.currency} onChange={(e) => setCard({ ...card, currency: e.target.value.toUpperCase() })} /></label>
          <label className="field compact"><span className="label">Role</span><input className="input" value={card.role} onChange={(e) => setCard({ ...card, role: e.target.value })} /></label>
          <label className="field compact"><span className="label">Rate / month</span><input className="input" value={card.rate} onChange={(e) => setCard({ ...card, rate: e.target.value })} /></label>
          <button className="btn btn-sm" disabled={!card.role || !card.rate} onClick={() => { setRates({ ...rates, [card.role]: card.rate }); setCard({ ...card, role: "", rate: "" }); }}>Add role</button>
          <button className="btn" disabled={!Object.keys(rates).length} onClick={() => attempt(() => hoiApi.putRateCard(card.name, { currency: card.currency, unit: "month", rates }), "Rate card saved as a new version")}>Save rate card</button>
          <span className="muted">{Object.keys(rates).length ? `Pending roles: ${Object.keys(rates).join(", ")}` : ""}</span>
        </fieldset>
        <fieldset style={{ border: 0, padding: 0, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "flex-end" }}>
          <legend className="label">Approved loaded cost (fully loaded, per month) — encrypted at rest</legend>
          <label className="field compact"><span className="label">Scope</span>
            <select className="select" value={cost.scope} onChange={(e) => setCost({ ...cost, scope: e.target.value })}><option value="role_band">Role band</option><option value="individual">Individual (coded id)</option></select></label>
          <label className="field compact"><span className="label">{cost.scope === "individual" ? "Coded identity" : "Role name"}</span><input className="input" value={cost.subject} onChange={(e) => setCost({ ...cost, subject: e.target.value })} /></label>
          <label className="field compact"><span className="label">Monthly cost</span><input className="input" type="password" autoComplete="off" value={cost.monthly_cost} onChange={(e) => setCost({ ...cost, monthly_cost: e.target.value })} /></label>
          <label className="field compact"><span className="label">Currency</span><input className="input" maxLength={3} value={cost.currency} onChange={(e) => setCost({ ...cost, currency: e.target.value.toUpperCase() })} /></label>
          <label className="field compact"><span className="label">Effective from</span><input className="input" type="date" value={cost.effective_from} onChange={(e) => setCost({ ...cost, effective_from: e.target.value })} /></label>
          <label className="field compact"><span className="label">Approved source ref</span><input className="input" value={cost.source} onChange={(e) => setCost({ ...cost, source: e.target.value })} /></label>
          <button className="btn" disabled={!cost.subject || !cost.monthly_cost || !cost.source} onClick={() => attempt(async () => { await hoiApi.addCosts([cost]); setCost({ ...cost, subject: "", monthly_cost: "" }); }, "Loaded cost stored (encrypted)")}>Add cost</button>
        </fieldset>
        <InlineError error={err} />
      </div>
    </details>
  );
}

function Simulator({ oid, months }: { oid: string; months: number }) {
  const { has } = useRoles();
  const list = useApi((s) => hoiApi.scenarios(oid, s), [oid]);
  const pols = useApi((s) => (has("manager", "finance") ? hoiApi.policies(s) : Promise.resolve({ policies: [] })), []);
  const cards = useApi((s) => (has("manager", "finance") ? hoiApi.rateCards(s) : Promise.resolve({ rate_cards: [] })), []);
  const data = useStale(list)?.scenarios ?? [];
  const [base, setBase] = useState("");
  const [m, setM] = useState(String(months));
  const [extra, setExtra] = useState("0");
  const [policy, setPolicy] = useState("");
  const [card, setCard] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const src = data.find((s) => s.scenario_id === (base || data[0]?.scenario_id));
  const polNames = pols.status === "success" ? Array.from(new Set(pols.data.policies.map((p) => p.name))) : [];
  const cardNames = cards.status === "success" ? Array.from(new Set(cards.data.rate_cards.map((p) => p.name))) : [];
  const rerun = async () => {
    if (!src?.assignments) return;
    setBusy(true); setErr(null);
    try {
      await hoiApi.createScenario(oid, {
        kind: src.kind, months: Number(m), project_direct_costs: extra,
        cost_policy_id: policy || polNames[0], rate_card_id: card || cardNames[0],
        assignments: src.assignments.map((a) => ({ requirement_id: a.requirement_id, resource_type: a.resource_type, coded_identity: a.coded_identity, fte: a.fte })),
      });
      list.reload();
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <div style={{ display: "grid", gap: 16 }}>
      {list.status === "loading" && !data.length && <Loading label="Loading scenarios" />}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status !== "loading" && !data.length && list.status !== "error" && <EmptyState title="No scenarios yet">Create scenarios from the Scenario Optimizer first.</EmptyState>}
      {has("manager", "finance") && data.length > 0 && (
        <section className="panel" aria-label="Sensitivity">
          <div className="panel-head"><h2>What-if: recalculate with new assumptions</h2></div>
          <div className="panel-body" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label className="field compact"><span className="label">Start from</span>
              <select className="select" value={src?.scenario_id ?? ""} onChange={(e) => setBase(e.target.value)} aria-label="Base scenario">
                {data.map((s) => <option key={s.scenario_id} value={s.scenario_id}>{s.kind} v{s.version_no} · {s.scenario_id}</option>)}</select></label>
            <label className="field compact"><span className="label">Months</span><input className="input" type="number" min={1} value={m} onChange={(e) => setM(e.target.value)} aria-label="Months" /></label>
            <label className="field compact"><span className="label">Extra direct project costs</span><input className="input" value={extra} onChange={(e) => setExtra(e.target.value)} aria-label="Extra direct project costs" /></label>
            <label className="field compact"><span className="label">Cost policy</span>
              <select className="select" value={policy || polNames[0] || ""} onChange={(e) => setPolicy(e.target.value)}>{polNames.map((n) => <option key={n}>{n}</option>)}</select></label>
            <label className="field compact"><span className="label">Rate card</span>
              <select className="select" value={card || cardNames[0] || ""} onChange={(e) => setCard(e.target.value)}>{cardNames.map((n) => <option key={n}>{n}</option>)}</select></label>
            <button className="btn btn-primary" disabled={busy} onClick={rerun}>{busy ? "Calculating…" : "Calculate new scenario"}</button>
          </div>
          <div className="panel-body"><InlineError error={err} /></div>
        </section>
      )}
      {data.map((s) => <Economics key={s.scenario_id} s={s} />)}
    </div>
  );
}

function Economics({ s }: { s: HoiScenario }) {
  const e = s.economics;
  const rev = e ? Number(e.revenue) : 0;
  return (
    <section className="panel" aria-label={`Economics ${s.kind} v${s.version_no}`}>
      <div className="panel-head"><h2 style={{ textTransform: "capitalize" }}>{s.kind} · v{s.version_no} · {s.months} months · {s.currency}</h2><Chip tone={s.status}>{pretty(s.status)}</Chip></div>
      <div className="panel-body">
        {s.approved_totals && !e && <div>Approved revenue total: <b>{s.approved_totals.revenue} {s.approved_totals.currency}</b></div>}
        {!s.calculable && <div className="inline-error">Not calculable — {(s.unresolved_detail ?? []).map((d) => d.message).join("; ") || s.unresolved_constraints.map(pretty).join(" · ") || "inputs missing"}. No figure is estimated.</div>}
        {e && (
          <>
            <section className="kpis">
              <Kpi label="Revenue" value={e.revenue} />
              {e.delivery_cost ? (
                <>
                  <Kpi label="Delivery cost" value={e.delivery_cost} />
                  <Kpi label="Gross profit" value={e.gross_profit} note={`gross margin ${e.gross_margin_pct ?? "n/a"}%`} />
                  <Kpi label="Contribution" value={e.contribution} note={`contribution margin ${e.contribution_margin_pct ?? "n/a"}%`} />
                </>
              ) : <Kpi label="Margin band" value={e.margin_band} note="cost detail is Finance-only" />}
            </section>
            {e.breakdown && (
              <table className="data" style={{ marginTop: 12 }}>
                <thead><tr><th>Cost component</th><th className="right">Amount ({e.currency})</th><th>Share of revenue</th></tr></thead>
                <tbody>{Object.entries(e.breakdown).filter(([, v]) => Number(v) !== 0).map(([k, v]) => (
                  <tr key={k}><td>{pretty(k)}</td><td className="right">{v}</td>
                    <td><div style={{ background: "var(--surface-sunk)", height: 8, borderRadius: 4 }}><div style={{ width: `${rev ? Math.min(100, (Number(v) / rev) * 100) : 0}%`, height: 8, borderRadius: 4, background: "var(--crimson)" }} /></div></td></tr>
                ))}</tbody>
              </table>
            )}
            {s.assumptions && <div className="muted" style={{ marginTop: 8 }}>Assumptions: {Object.entries(s.assumptions).map(([k, v]) => `${pretty(k)}: ${typeof v === "string" ? v : JSON.stringify(v)}`).join(" · ")} · calc {s.calc_version}</div>}
          </>
        )}
      </div>
    </section>
  );
}
