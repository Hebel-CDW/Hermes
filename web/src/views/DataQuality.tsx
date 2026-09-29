import { dataQualityApi, taxonomyApi } from "../api/endpoints";
import { ApiError } from "../api/http";
import type { DataQuality as DQ, TaxonomyPending } from "../api/types";
import { int, rejectionText, shortTime } from "../lib/format";
import { hasRole, useAuth } from "../lib/auth";
import { useApi } from "../lib/useApi";
import { Bar, Kpi, PageHead } from "../ui/Bits";
import { PipelineStates } from "../ui/Pipeline";
import { EmptyState, ErrorState, Loading } from "../ui/States";
import { useState } from "react";

export default function DataQuality() {
  const q = useApi((s) => dataQualityApi.get(s), []);
  const inbox = useApi(async (s) => {
    try {
      return await taxonomyApi.pending(s);
    } catch (err) {
      if (err instanceof ApiError) return { pending: [] } satisfies TaxonomyPending;
      throw err;
    }
  }, []);
  return (
    <>
      <PageHead
        trail={["Governance", "Data quality"]}
        title="Data quality"
        lede="What was imported, validated, mapped to governed skills and scored. Aggregate counts only — no names, raw rows or client labels."
      />
      {q.status === "loading" && <Loading label="Loading data quality" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && (
        <Body dq={q.data} inbox={inbox.status === "success" ? inbox.data : { pending: [] }} onInboxChange={inbox.reload} />
      )}
    </>
  );
}

function BarList({ rows, tone, testid }: { rows: [string, number][]; tone?: "crimson" | "ink"; testid: string }) {
  const max = Math.max(1, ...rows.map(([, n]) => n));
  return (
    <div data-testid={testid}>
      {rows.map(([label, n]) => (
        <div className="bar-row" key={label}>
          <span className="ink-2">{label}</span>
          <Bar value={n / max} tone={tone} />
          <span className="count">{int(n)}</span>
        </div>
      ))}
    </div>
  );
}

function Body({ dq, inbox, onInboxChange }: { dq: DQ; inbox: TaxonomyPending; onInboxChange: () => void }) {
  const ing = dq.ingestion;
  const excluded = ing ? Object.values(ing.excluded_field_occurrences).reduce((a, b) => a + b, 0) : null;
  return (
    <>
      <div className="chips" style={{ marginBottom: 16 }}>
        <span className={`chip ${dq.data_classification === "real" ? "chip-crimson" : "chip-teal"}`}>
          {dq.data_classification === "real" ? "Real workforce data" : dq.data_classification === "synthetic" ? "Synthetic data" : "Unclassified"}
        </span>
        {ing && (
          <span className="chip">
            {ing.source_name} · ingested {shortTime(ing.ingested_at)}
          </span>
        )}
      </div>

      <PipelineStates dq={dq} />

      <TaxonomyInbox rows={inbox.pending} onChange={onInboxChange} />

      {!ing ? (
        <div className="section">
          <EmptyState title="No workbook ingestion recorded">
            This database has no governed workbook import. Real workforce data enters only through the Phase 8 real-data ingestion command.
          </EmptyState>
        </div>
      ) : (
        <>
          <section className="kpis kpis-dense section" aria-label="Ingestion figures">
            <Kpi label="People imported" value={int(dq.database.people_imported)} note="coded identities" />
            <Kpi label="Accepted cells" value={int(ing.cells_accepted)} note={`${int(ing.cells_processed)} processed`} />
            <Kpi label="Rejected cells" value={int(ing.cells_rejected)} note="with a machine reason" />
            <Kpi label="Pending mappings" value={int(ing.labels.pending)} note={`of ${int(ing.labels.skill_labels)} workbook skill labels`} />
            <Kpi label="Mapped skills" value={int(ing.labels.mapped)} note={`${int(dq.canonical_skills)} canonical skills`} />
            <Kpi label="Certificates" value={int(dq.certificates.staged)} note={`${int(dq.certificates.exact_mapped)} exact code matches`} />
            <Kpi label="Excluded fields" value={int(excluded)} note="column occurrences" />
          </section>

          <div className="grid cols-2 section">
            <section className="panel">
              <div className="panel-head">
                <h2>Rejection categories</h2>
                <span className="muted" style={{ fontSize: 12 }}>
                  {int(ing.cells_rejected)} rejected
                </span>
              </div>
              <div className="panel-body">
                {Object.keys(ing.rejections_by_reason).length === 0 ? (
                  <span className="muted">No rejections.</span>
                ) : (
                  <BarList
                    testid="rejections"
                    tone="crimson"
                    rows={Object.entries(ing.rejections_by_reason)
                      .sort((a, b) => b[1] - a[1])
                      .map(([code, n]) => [rejectionText(code), n])}
                  />
                )}
              </div>
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Taxonomy governance</h2>
                <span className="muted" style={{ fontSize: 12 }}>
                  Workbook labels
                </span>
              </div>
              <div className="panel-body">
                <BarList
                  testid="labels"
                  rows={[
                    ["Mapped (governed)", ing.labels.mapped ?? 0],
                    ["Pending approval", ing.labels.pending ?? 0],
                    ["Rejected · client / account", ing.labels.rejected.client_account ?? 0],
                    ["Rejected · soft skill", ing.labels.rejected.soft_skill ?? 0],
                    ["Rejected · culture fit", ing.labels.rejected.culture_fit ?? 0],
                  ]}
                />
                <p className="hint" style={{ marginBottom: 0 }}>
                  Pending and rejected labels never enter scoring. Mappings are never inferred by fuzzy matching or AI.
                </p>
              </div>
            </section>
          </div>

          <div className="grid cols-2 section">
            <section className="panel">
              <div className="panel-head">
                <h2>Certificates</h2>
              </div>
              <div className="panel-body">
                <BarList
                  testid="certificates"
                  rows={[
                    ["Exact code match", dq.certificates.exact_mapped],
                    ["Pending mapping", dq.certificates.pending],
                    ["Earned date recorded", dq.certificates.with_earned_at],
                    ["Promoted to evidence", dq.certificates.promoted],
                  ]}
                />
                <p className="hint" style={{ marginBottom: 0 }}>
                  Earned dates are never invented; a certificate scores only after a human supplies its date.
                </p>
              </div>
            </section>

            <section className="panel">
              <div className="panel-head">
                <h2>Approved label mappings</h2>
              </div>
              {ing.labels.mapped_trace.length === 0 ? (
                <div className="panel-body">
                  <span className="muted">No workbook label has an approved canonical mapping.</span>
                </div>
              ) : (
                <ul className="activity" data-testid="mapped-trace">
                  {ing.labels.mapped_trace.map((m) => (
                    <li key={m.label}>
                      <span>
                        {m.label} → <span className="mono">{m.skill_id}</span>
                      </span>
                      <span className="chip">{m.mapped_by}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <div className="footer-meta">
            <span>
              Run <span className="mono">{ing.run_id}</span>
            </span>
            <span>Baseline ratings are stored for governance only and are never scored.</span>
          </div>
        </>
      )}
    </>
  );
}

function TaxonomyInbox({ rows, onChange }: { rows: TaxonomyPending["pending"]; onChange: () => void }) {
  const { session } = useAuth();
  const admin = hasRole(session, "admin");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function decide(alias: string, decision: "approve" | "reject", skillId?: string) {
    setBusy(`${alias}:${decision}`);
    setError(null);
    try {
      await taxonomyApi.resolve(alias, decision === "approve" ? { decision, skill_id: skillId } : { decision });
      onChange();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update mapping");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="panel section" data-testid="taxonomy-inbox">
      <div className="panel-head">
        <h2>Taxonomy inbox</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          Human approve only · mapped_by=human
        </span>
      </div>
      {rows.length === 0 ? (
        <div className="panel-body muted">No pending skill labels. Approvals never come from fuzzy matching or an LLM.</div>
      ) : (
        <ul className="activity">
          {rows.map((row) => (
            <li key={row.alias_label}>
              <span>
                {row.alias_label}
                {row.proposed_skill_id && (
                  <>
                    {" "}
                    → <span className="mono">{row.proposed_skill_id}</span>
                  </>
                )}
              </span>
              {admin && (
                <span style={{ display: "flex", gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={!row.proposed_skill_id || busy !== null}
                    onClick={() => decide(row.alias_label, "approve", row.proposed_skill_id)}
                  >
                    Approve
                  </button>
                  <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={() => decide(row.alias_label, "reject")}>
                    Reject
                  </button>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {error && <p className="hint">{error}</p>}
    </section>
  );
}
