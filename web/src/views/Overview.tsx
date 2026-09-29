import { dataQualityApi, excelSunsetApi, overviewApi } from "../api/endpoints";
import { ApiError } from "../api/http";
import type { ExcelSunset, Overview as OverviewData } from "../api/types";
import { fixed, int, pct, shortTime } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Bar, Kpi, PageHead, Ring, StatusChip } from "../ui/Bits";
import { PipelineStates } from "../ui/Pipeline";
import { EmptyState, ErrorState, Loading } from "../ui/States";

export default function Overview() {
  const q = useApi(async (s) => {
    const [overview, dq] = await Promise.all([overviewApi.get(s), dataQualityApi.get(s)]);
    let sunset: ExcelSunset | null = null;
    try {
      sunset = await excelSunsetApi.get(s);
    } catch (err) {
      if (!(err instanceof ApiError)) throw err;
    }
    return { overview, dq, sunset };
  }, []);
  return (
    <>
      <PageHead trail={["Overview"]} title="Overview" lede="Where the team stands today: who has proof of which skills." />
      {q.status === "loading" && <Loading label="Loading overview" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (q.data.overview.people === 0 ? (
          <EmptyState title="No workforce data yet">Ingest governed evidence to populate the capability matrix.</EmptyState>
        ) : (
          <OverviewBody data={q.data.overview} dq={q.data.dq} sunset={q.data.sunset} />
        ))}
    </>
  );
}

function OverviewBody({ data, dq, sunset }: { data: OverviewData; dq: import("../api/types").DataQuality; sunset: ExcelSunset | null }) {
  const openRequests = data.requests_by_status.open ?? 0;
  const statuses = Object.entries(data.requests_by_status);
  return (
    <>
      {dq.ingestion && (
        <div style={{ marginBottom: 16 }}>
          <PipelineStates dq={dq} />
        </div>
      )}
      <section className="kpis" aria-label="Key figures">
        <Kpi label="People" value={int(data.people)} note={`${int(data.identities_with_evidence)} with skill evidence`} />
        <Kpi label="Skills tracked" value={int(data.governed_skills)} note={`${int(data.skill_records)} skill records`} />
        <Kpi
          label="People with proven skills"
          value={`${fixed(data.demonstrated_coverage.coverage_pct, 1)}%`}
          note={`${int(data.demonstrated_coverage.with_demonstrated)} of ${int(data.demonstrated_coverage.pilot_size)} with proof from real work`}
        />
        <Kpi label="Open requests" value={int(openRequests)} note={`${int(data.role_profiles)} role profiles`} />
      </section>

      <details className="section tech-details">
      <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>Technical details (data pipeline and Excel retirement)</summary>
      <section className="kpis kpis-dense section" aria-label="Survey versus living">
        <Kpi label="Imported (survey)" value={int(dq.pipeline.imported)} note="2025 workbook identities" />
        <Kpi label="Scored (living)" value={int(dq.pipeline.scored)} note="evidence-derived identities" />
        <Kpi
          label="2026 workbook"
          value={sunset?.next_workbook_allowed ? "Allowed" : "Frozen"}
          note={sunset ? `survey year ${sunset.survey_year_frozen}` : "policy on server"}
        />
        <Kpi
          label="Excel kill gate"
          value={sunset?.ready_to_retire_excel ? "Ready" : "Open"}
          note={sunset ? `${fixed(sunset.criteria.pilot_coverage_pct, 1)}% pilot coverage` : "coverage pending"}
        />
      </section>
      </details>

      <div className="grid cols-3 section">
        <section className="panel">
          <div className="panel-head">
            <h2>Evidence readiness</h2>
          </div>
          <div className="panel-body ring-wrap">
            {data.identities_with_evidence === 0 ? (
              <div className="state empty" style={{ padding: 16, width: "100%" }} data-testid="overview-unscored">
                <h3>No scored capability</h3>
                <p>No coded identity has evidence-derived skill records yet.</p>
              </div>
            ) : (
              <Ring value={data.skill_coverage_ratio} label="Identities with skill evidence" />
            )}
            <div style={{ flex: 1, minWidth: 160 }}>
              <div className="label">People with proof of skills</div>
              <p className="ink-2" style={{ margin: "6px 0 0" }}>
                {int(data.identities_with_evidence)} of {int(data.people)} people have at least one skill backed by real work.
              </p>
            </div>
          </div>
        </section>

        <section className="panel" style={{ gridColumn: "span 2" }}>
          <div className="panel-head">
            <h2>Capability coverage by domain</h2>
            <span className="muted" style={{ fontSize: 12 }}>
              Share of people with evidence in the domain
            </span>
          </div>
          <div className="panel-body" style={{ paddingTop: 8, paddingBottom: 8 }}>
            {data.domains.length === 0 && <p className="muted">No domains in the ontology.</p>}
            {data.domains.map((d) => (
              <div className="domain-bar" key={d.domain_id}>
                <span>{d.name}</span>
                <span className="muted num hc" title="Identities with evidence">
                  {int(d.identities_with_evidence)} people
                </span>
                <Bar value={d.coverage_ratio} />
                <span className="num" style={{ textAlign: "right" }}>
                  {pct(d.coverage_ratio)}
                </span>
              </div>
            ))}
          </div>
        </section>
      </div>

      <div className="grid cols-2 section">
        <section className="panel">
          <div className="panel-head">
            <h2>Staffing requests</h2>
          </div>
          {statuses.length === 0 ? (
            <div className="panel-body muted">No staffing requests have been ranked yet.</div>
          ) : (
            <ul className="activity">
              {statuses.map(([status, count]) => (
                <li key={status}>
                  <StatusChip status={status} />
                  <span className="num">{int(count)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <h2>Recent activity</h2>
            <span className={`chip ${data.audit_chain_verified ? "chip-ok" : "chip-crimson"}`}>
              {data.audit_chain_verified ? "Audit trail intact" : "Audit trail check failed"}
            </span>
          </div>
          {data.recent_activity.length === 0 ? (
            <div className="panel-body muted">No audit events recorded.</div>
          ) : (
            <ul className="activity">
              {data.recent_activity.map((a) => (
                <li key={a.seq}>
                  <span>
                    <span className="mono muted" style={{ marginRight: 10 }}>
                      #{a.seq}
                    </span>
                    {a.event_type.replace(/_/g, " ")}
                  </span>
                  <span className="muted num">{shortTime(a.created_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <details className="footer-meta tech-details">
        <summary style={{ cursor: "pointer" }}>Technical details</summary>
        <span>
          Scoring config <span className="mono">{data.scoring_config_version}</span>
        </span>
        <span>
          Latest computation run <span className="mono">{data.latest_computation_run_id ?? "none"}</span>
        </span>
      </details>
    </>
  );
}
