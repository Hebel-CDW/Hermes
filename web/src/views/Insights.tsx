import { matrixApi, overviewApi } from "../api/endpoints";
import { fixed, int, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Bar, Kpi, PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, Loading } from "../ui/States";

export default function Insights() {
  const q = useApi(
    async (s) => {
      const [overview, dashboard, runs] = await Promise.all([overviewApi.get(s), matrixApi.dashboard(s), matrixApi.runs(s)]);
      return { overview, dashboard, runs: runs.runs };
    },
    [],
  );
  return (
    <>
      <PageHead
        trail={["Analytics", "Enterprise observability"]}
        title="Insights"
        lede="Domain coverage, evidence freshness and computation history, as reported by the API."
      />
      {q.status === "loading" && <Loading label="Loading insights" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (() => {
          const { overview, dashboard, runs } = q.data;
          const freshness = Object.entries(dashboard.avg_freshness_by_skill);
          return (
            <>
              <section className="kpis">
                <Kpi label="Governed skills" value={int(overview.governed_skills)} />
                <Kpi label="Skill records" value={int(overview.skill_records)} />
                <Kpi label="Identities with evidence" value={pct(overview.skill_coverage_ratio)} note={`${overview.identities_with_evidence} of ${overview.people}`} />
                <Kpi label="Computation runs" value={int(runs.length)} />
              </section>

              <section className="panel section">
                <div className="panel-head">
                  <h2>Capability by domain</h2>
                </div>
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Domain</th>
                        <th className="right">Skills</th>
                        <th className="right">Identities</th>
                        <th style={{ minWidth: 160 }}>Coverage</th>
                        <th className="right">Mean level</th>
                        <th className="right">Mean confidence</th>
                        <th className="right">Mean freshness</th>
                      </tr>
                    </thead>
                    <tbody>
                      {overview.domains.map((d) => (
                        <tr key={d.domain_id}>
                          <td>{d.name}</td>
                          <td className="right num">{d.skill_count}</td>
                          <td className="right num">{d.identities_with_evidence}</td>
                          <td>
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 56px", gap: 10, alignItems: "center" }}>
                              <Bar value={d.coverage_ratio} />
                              <span className="num" style={{ textAlign: "right" }}>
                                {pct(d.coverage_ratio)}
                              </span>
                            </div>
                          </td>
                          <td className="right num">{d.mean_level === null ? "—" : fixed(d.mean_level, 2)}</td>
                          <td className="right num">{pct(d.mean_confidence)}</td>
                          <td className="right num">{pct(d.mean_freshness)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <div className="grid cols-2 section">
                <section className="panel">
                  <div className="panel-head">
                    <h2>Evidence freshness by skill</h2>
                  </div>
                  <div className="panel-body">
                    {freshness.length === 0 ? (
                      <span className="muted">No skill records to report.</span>
                    ) : (
                      freshness.map(([skill, value]) => (
                        <div key={skill} className="metric-row">
                          <span className="ink-2">{skill}</span>
                          <span className="num">{pct(value)}</span>
                          <Bar value={value} tone={value < 0.5 ? "crimson" : undefined} />
                        </div>
                      ))
                    )}
                  </div>
                </section>
                <section className="panel">
                  <div className="panel-head">
                    <h2>Computation runs</h2>
                    <span className="muted" style={{ fontSize: 12 }}>
                      Newest first
                    </span>
                  </div>
                  {runs.length === 0 ? (
                    <div className="panel-body muted">No computation runs recorded.</div>
                  ) : (
                    <ul className="activity">
                      {runs.map((r, i) => (
                        <li key={r}>
                          <span className="mono">{r}</span>
                          {i === 0 && <span className="chip chip-teal">Latest</span>}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>

              <div className="section">
                <EmptyState title="Trend analytics not available">
                  The API does not yet expose time-series capability metrics, so no velocity or demand trend is shown.
                </EmptyState>
              </div>
            </>
          );
        })()}
    </>
  );
}
