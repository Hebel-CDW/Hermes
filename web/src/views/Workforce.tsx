import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { workforceApi } from "../api/endpoints";
import type { Workforce as WorkforceData } from "../api/types";
import { int } from "../lib/format";
import { useNames } from "../lib/names";
import { useApi } from "../lib/useApi";
import { Levels, Metric, PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, Loading } from "../ui/States";

export default function Workforce() {
  const q = useApi((s) => workforceApi.get(s), []);
  return (
    <>
      <PageHead
        trail={["Workforce", "Capability topology"]}
        title="Workforce"
        lede="Everyone, grouped by their main skill area, with how many skills each person has proof for and how sure Hermes is."
      />
      {q.status === "loading" && <Loading label="Loading workforce" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (q.data.identities.length === 0 ? (
          <EmptyState title="No coded identities">The identity map is empty. Ingest synthetic fixtures first.</EmptyState>
        ) : (
          <WorkforceBody data={q.data} />
        ))}
    </>
  );
}

const UNASSIGNED = "__none__";

/** Group scored people by their main domain. Layout only: every value shown comes from the API. */
function groupByDomain(data: WorkforceData) {
  const scored = data.identities.filter((i) => i.skill_count > 0);
  const groups = [...data.domains.map((d) => ({ key: d.domain_id, name: d.name })), { key: UNASSIGNED, name: "No evidence" }]
    .map((g) => ({ ...g, members: scored.filter((i) => (i.primary_domain ?? UNASSIGNED) === g.key) }))
    .filter((g) => g.members.length > 0);
  return groups;
}

const UNSCORED_PAGE = 60;

function WorkforceBody({ data }: { data: WorkforceData }) {
  const { label } = useNames();
  const scored = data.identities.filter((i) => i.skill_count > 0);
  const unscored = data.identities.filter((i) => i.skill_count === 0);
  const [selected, setSelected] = useState<string>((scored[0] ?? data.identities[0]).coded_identity);
  const [filter, setFilter] = useState("");
  const groups = useMemo(() => groupByDomain(data), [data]);
  const current = data.identities.find((i) => i.coded_identity === selected) ?? data.identities[0];
  const domainName = (id: string) => data.domains.find((d) => d.domain_id === id)?.name ?? id;
  const needle = filter.trim().toLowerCase();
  const matches = unscored.filter((i) => !needle || i.coded_identity.toLowerCase().includes(needle));
  return (
    <div className="split">
      <div style={{ minWidth: 0 }}>
        {scored.length === 0 ? (
          <div className="state empty" data-testid="no-scored-capability">
            <h3>No scored capability</h3>
            <p>
              {int(data.identities.length)} coded identities are imported, and none has evidence-derived skill records. Workbook ratings are
              baseline data and are never shown as capability.
            </p>
          </div>
        ) : (
        <div className="atlas" role="group" aria-label="Workforce topology">
          <div className="atlas-grid">
            {groups.map((g) => (
              <section key={g.key} className="atlas-domain" aria-label={g.name}>
                <h3>
                  {g.name} <span className="muted num">{g.members.length}</span>
                </h3>
                <div className="people-list">
                  {g.members.map((id) => (
                    <button
                      key={id.coded_identity}
                      type="button"
                      className={`person-row${id.coded_identity === current.coded_identity ? " is-active" : ""}`}
                      aria-pressed={id.coded_identity === current.coded_identity}
                      aria-label={`${id.coded_identity}, ${id.skill_count} skills`}
                      onClick={() => setSelected(id.coded_identity)}
                    >
                      <span className="person-row-name">{label(id.coded_identity)}</span>
                      <span className="person-row-meta">
                        {id.skill_count} skill{id.skill_count === 1 ? "" : "s"} · {id.mean_confidence === null ? "no proof yet" : `${Math.round(id.mean_confidence * 100)}% sure`}
                      </span>
                    </button>
                  ))}
                </div>
              </section>
            ))}
          </div>
          <div className="canvas-legend">
            <span>
              {int(scored.length)} scored of {int(data.identities.length)} coded identities
            </span>
            <span>Grouped by each person's main skill area. Pick someone to see their skills on the right.</span>
          </div>
        </div>
        )}
        {unscored.length > 0 && (
          <section className="panel section" aria-label="Identities without scored capability">
            <div className="panel-head">
              <h2>Coded identities without scored capability</h2>
              <span className="muted" style={{ fontSize: 12 }} data-testid="unscored-count">
                {int(unscored.length)} coded identities
              </span>
            </div>
            <div className="panel-body">
              <input
                name="identity_filter"
                className="input mono"
                placeholder="Filter coded identities"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                aria-label="Filter coded identities"
                style={{ marginBottom: 12 }}
              />
              <div className="id-grid">
                {matches.slice(0, UNSCORED_PAGE).map((i) => (
                  <button key={i.coded_identity} className="id-chip" aria-pressed={i.coded_identity === current.coded_identity} onClick={() => setSelected(i.coded_identity)}>
                    {label(i.coded_identity)}
                  </button>
                ))}
              </div>
              <p className="hint" style={{ marginBottom: 0 }}>
                Showing {int(Math.min(matches.length, UNSCORED_PAGE))} of {int(matches.length)}. Coded identities only; names are available solely through governed identity resolution.
              </p>
            </div>
          </section>
        )}
      </div>

      <aside className="panel" aria-label="Inspection ledger">
        <div className="panel-head">
          <span className="label">Inspection ledger</span>
        </div>
        <div className="panel-body">
          <div className="label">Target identity</div>
          <div className="inspect-title" data-testid="selected-identity">
            {current.coded_identity}
          </div>
          {label(current.coded_identity) !== current.coded_identity && (
            <div style={{ fontWeight: 600, marginBottom: 8 }}>{label(current.coded_identity)}</div>
          )}
          <div className="chips" style={{ margin: "10px 0 18px" }}>
            {current.domains.length === 0 && <span className="chip">No domain evidence</span>}
            {current.domains.map((d) => (
              <span className="chip chip-teal" key={d}>
                {domainName(d)}
              </span>
            ))}
          </div>
          {current.skill_count === 0 ? (
            <div className="state empty" style={{ padding: 16 }} data-testid="ledger-unscored">
              <h3>No scored capability</h3>
              <p>This identity has no evidence-derived skill records.</p>
            </div>
          ) : (
          <>
          <dl className="dl" style={{ marginBottom: 18 }}>
            <dt>Skill records</dt>
            <dd className="num">{int(current.skill_count)}</dd>
            <dt>Highest level</dt>
            <dd className="num">{current.max_level ?? "—"}</dd>
          </dl>
          <Metric label="Mean confidence" value={current.mean_confidence} />
          <Metric label="Mean freshness" value={current.mean_freshness} tone="ink" />
          <div className="label" style={{ margin: "22px 0 8px" }}>
            Skills
          </div>
          {current.skills.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>
              No inferred skills for this identity.
            </p>
          ) : (
            <div className="grid" style={{ gap: 10 }}>
              {current.skills.map((s) => (
                <Link key={s.skill_id} to={`/skills?skill=${encodeURIComponent(s.skill_id)}`} style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                  <span>{s.skill_name}</span>
                  <Levels level={s.proficiency} />
                </Link>
              ))}
            </div>
          )}
          </>
          )}
          <Link className="btn" to="/matrix" style={{ width: "100%", marginTop: 20 }}>
            Open in skill matrix
          </Link>
        </div>
      </aside>
    </div>
  );
}
