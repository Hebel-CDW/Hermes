import { useState } from "react";
import { hoiApi } from "../../api/endpoints";
import type { HoiScenario } from "../../api/types";
import { useApi, useStale } from "../../lib/useApi";
import { PageHead } from "../../ui/Bits";
import { useToasts } from "../../ui/Fx";
import { EmptyState, ErrorState, InlineError, Loading } from "../../ui/States";
import { Chip, OppGate, OppPicker, SyntheticBanner, download, pretty, useRoles, useSelectedOpp } from "./common";

export default function Scenarios() {
  const sel = useSelectedOpp();
  return (
    <>
      <PageHead
        trail={["Opportunity Intelligence", "Scenario Optimizer"]}
        title="Scenario Optimizer"
        lede="Compare internal, external and hybrid staffing. Qualification and capacity are applied first; economics are compared second. Nobody is assigned automatically."
      />
      <div className="notice warn" role="note" style={{ marginBottom: 12 }}>
        Commercial figures never change technical fitness ranking. Internal slots follow fitness rank among eligible candidates only. Risk flags are
        rule-based indicators, not probabilities.
      </div>
      <OppGate sel={sel}>
        {(opp) => (
          <>
            <div className="chip-row"><OppPicker opps={sel.opps} selected={sel.selected} select={sel.select} /></div>
            <SyntheticBanner show={opp.is_synthetic} />
            <Body oid={opp.opportunity_id} />
          </>
        )}
      </OppGate>
    </>
  );
}

function Body({ oid }: { oid: string }) {
  const { has } = useRoles();
  const list = useApi((s) => hoiApi.scenarios(oid, s), [oid]);
  const canCompare = has("manager", "finance"); // sales/hr/admin only read scenarios; do not request Finance parameters
  const pols = useApi((s) => (canCompare ? hoiApi.policies(s) : Promise.resolve({ policies: [] })), [canCompare]);
  const cards = useApi((s) => (canCompare ? hoiApi.rateCards(s) : Promise.resolve({ rate_cards: [] })), [canCompare]);
  const [policy, setPolicy] = useState("");
  const [card, setCard] = useState("");
  const [notes, setNotes] = useState<string[]>([]);
  const [err, setErr] = useState<Error | null>(null);
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState<string>("");
  const { push, host } = useToasts();
  const data = useStale(list)?.scenarios ?? [];
  const polNames = pols.status === "success" ? Array.from(new Set(pols.data.policies.map((p) => p.name))) : [];
  const cardNames = cards.status === "success" ? Array.from(new Set(cards.data.rate_cards.map((c) => c.name))) : [];
  const compare = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await hoiApi.compare(oid, { cost_policy_id: policy || polNames[0], rate_card_id: card || cardNames[0] });
      setNotes(r.notes);
      push("Three draft scenarios calculated. None is assigned.", "ok");
      list.reload();
    } catch (e) { setErr(e as Error); } finally { setBusy(false); }
  };
  return (
    <div style={{ display: "grid", gap: 16 }}>
      {host}
      {has("manager", "finance") && (
        <section className="panel" aria-label="Compare scenarios">
          <div className="panel-body" style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
            <label className="field compact"><span className="label">Cost policy (Finance-approved)</span>
              <select className="select" value={policy || polNames[0] || ""} onChange={(e) => setPolicy(e.target.value)} aria-label="Cost policy">
                {polNames.map((n) => <option key={n}>{n}</option>)}
              </select></label>
            <label className="field compact"><span className="label">Rate card</span>
              <select className="select" value={card || cardNames[0] || ""} onChange={(e) => setCard(e.target.value)} aria-label="Rate card">
                {cardNames.map((n) => <option key={n}>{n}</option>)}
              </select></label>
            <button className="btn btn-primary" disabled={busy || !polNames.length || !cardNames.length} onClick={compare}>{busy ? "Calculating…" : "Compare internal / external / hybrid"}</button>
            {(!polNames.length || !cardNames.length) && <span className="muted">Finance must publish a cost policy and a rate card first (Commercial Simulator).</span>}
          </div>
        </section>
      )}
      <InlineError error={err} />
      {notes.map((n) => <div className="muted" key={n}>{n}</div>)}
      {list.status === "loading" && !data.length && <Loading label="Loading scenarios" />}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status !== "loading" && !data.length && list.status !== "error" && (
        <EmptyState title="No scenarios yet">Approve the requirements and run the internal match, then compare.</EmptyState>
      )}
      <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(280px,1fr))" }}>
        {data.map((s) => <Card key={s.scenario_id} s={s} active={open === s.scenario_id} onOpen={() => setOpen(s.scenario_id)} />)}
      </div>
      {data.filter((s) => s.scenario_id === open).map((s) => <Detail key={s.scenario_id} oid={oid} s={s} reload={list.reload} />)}
    </div>
  );
}

function Card({ s, active, onOpen }: { s: HoiScenario; active: boolean; onOpen: () => void }) {
  const e = s.economics;
  return (
    <section className="panel" aria-label={`${s.kind} scenario`} style={active ? { outline: "2px solid var(--crimson)" } : undefined}>
      <div className="panel-head"><h2 style={{ textTransform: "capitalize" }}>{s.kind} <span className="muted">v{s.version_no}</span></h2><Chip tone={s.status}>{pretty(s.status)}</Chip></div>
      <div className="panel-body" style={{ display: "grid", gap: 6 }}>
        {s.assignment_summary && <div>{s.assignment_summary.internal} internal · {s.assignment_summary.external} external</div>}
        {s.approved_totals && <div><b>Approved total revenue:</b> {s.approved_totals.revenue} {s.approved_totals.currency} over {s.approved_totals.months} months</div>}
        {e && <div>Revenue <b>{e.revenue}</b> {e.currency} · margin {e.gross_margin_pct != null ? `${e.gross_margin_pct}%` : e.margin_band}</div>}
        {!s.calculable && !s.approved_totals && <Chip tone="unknown">not calculable — inputs missing</Chip>}
        {s.risk && <div>Risk <Chip tone={s.risk.level}>{s.risk.level}</Chip></div>}
        {s.lead_time_weeks && <div>Lead time: {s.lead_time_weeks.overall_weeks != null ? `${s.lead_time_weeks.overall_weeks} weeks` : "unknown"}</div>}
        {s.unresolved_constraints.length > 0 && (
          <div className="inline-error" role="note">
            {(s.unresolved_detail ?? s.unresolved_constraints.map((c) => ({ code: c, message: pretty(c) }))).map((d) => <div key={d.code}>{d.message}</div>)}
          </div>
        )}
        {s.override_required && <Chip tone="medium">override reason needed</Chip>}
        <button className="btn btn-sm" onClick={onOpen}>Open details</button>
      </div>
    </section>
  );
}

function Detail({ oid, s, reload }: { oid: string; s: HoiScenario; reload: () => void }) {
  const { has } = useRoles();
  const [reason, setReason] = useState("");
  const [override, setOverride] = useState("");
  const [err, setErr] = useState<Error | null>(null);
  const { push, host } = useToasts();
  const lane = has("manager") ? "delivery" : has("finance") ? "finance" : has("hr") ? "hr" : null;
  const act = async (outcome: "approved" | "rejected") => {
    setErr(null);
    try {
      await hoiApi.approve(oid, { scenario_id: s.scenario_id, approver_role: lane, outcome, reason: reason || null, override_reason: override || null });
      push(`Decision recorded: ${outcome}`, "ok");
      reload();
    } catch (e) { setErr(e as Error); }
  };
  const exp = async (format: "json" | "markdown") => {
    setErr(null);
    try {
      const r = await hoiApi.exportReport(oid, s.scenario_id, format);
      if (format === "json") download(`${s.scenario_id}.json`, JSON.stringify(r.report, null, 2), "application/json");
      else download(`${s.scenario_id}.md`, r.content ?? "", "text/markdown");
    } catch (e) { setErr(e as Error); }
  };
  return (
    <section className="panel" aria-label="Scenario details">
      {host}
      <div className="panel-head"><h2>Scenario {s.scenario_id}</h2><span className="muted mono">calc {s.calc_version} · input {s.input_hash.slice(0, 10)}…</span></div>
      <div className="panel-body" style={{ display: "grid", gap: 12 }}>
        {s.assignments && (
          <table className="data">
            <thead><tr><th>Slot</th><th>Type</th><th>Coded identity</th><th>FTE</th><th>Fitness rank</th><th>Cost basis</th></tr></thead>
            <tbody>{s.assignments.map((a, i) => (
              <tr key={i}><td className="mono">{a.requirement_id.slice(-6)}</td><td>{a.resource_type}</td><td className="mono">{a.coded_identity ?? "external slot (not Hermes-scored)"}</td>
                <td>{a.fte}</td><td>{a.fitness_rank ?? "—"}</td><td>{a.cost_basis ? pretty(a.cost_basis) : "restricted"}</td></tr>
            ))}</tbody>
          </table>
        )}
        {s.risk && s.risk.flags.length > 0 && <div>Flags: {s.risk.flags.map((f) => <Chip key={f} tone="medium">{pretty(f)}</Chip>)} <span className="muted">({s.risk.basis})</span></div>}
        {s.capacity && s.capacity.length > 0 && <div className="muted">Capacity: {s.capacity.map((c) => `${c.coded_identity} ${c.requested_fte}/${c.available_fte ?? "?"} FTE`).join(" · ")}</div>}
        <div>
          <div className="label">Approvals</div>
          {s.approvals.required.map((r) => (
            <span key={r} style={{ marginRight: 8 }}><Chip tone={s.approvals.latest[r] ?? "draft"}>{r}: {s.approvals.latest[r] ?? "pending"}</Chip></span>
          ))}
          {s.uses_individual_cost && <div className="muted">HR authorization is required because individual compensation data was used.</div>}
        </div>
        {lane && s.status !== "approved" && (
          <div style={{ display: "grid", gap: 8, maxWidth: 520 }}>
            <label className="field compact"><span className="label">Reason (required to reject)</span><input className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
            {s.override_required && lane === "delivery" && (
              <label className="field compact"><span className="label">Override reason — a higher-ranked eligible candidate was not selected</span><input className="input" value={override} onChange={(e) => setOverride(e.target.value)} /></label>
            )}
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-primary" onClick={() => act("approved")}>Approve as {lane}</button>
              <button className="btn" onClick={() => act("rejected")}>Reject</button>
            </div>
          </div>
        )}
        <InlineError error={err} />
        {s.status === "approved" && (
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" onClick={() => exp("json")}>Export report (JSON)</button>
            <button className="btn" onClick={() => exp("markdown")}>Export report (Markdown)</button>
          </div>
        )}
        <div className="muted">Approval records a decision. It does not assign anyone or write to any HR or allocation system.</div>
      </div>
    </section>
  );
}
