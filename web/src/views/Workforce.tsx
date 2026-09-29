import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { workforceApi } from "../api/endpoints";
import type { Workforce as WorkforceData, WorkforceIdentity } from "../api/types";
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
        lede="Everyone, grouped by their main area. Bigger circles mean more skills; a fuller ring means stronger proof."
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

const W = 960;
const UNASSIGNED = "__none__";

type Placed = { id: WorkforceIdentity; x: number; y: number; r: number };

/** Layout only: positions are geometry; the encoded values (skill_count, mean_confidence) come from the API. */
function layout(data: WorkforceData) {
  data = { ...data, identities: data.identities.filter((i) => i.skill_count > 0) };
  const clusters = [...data.domains.map((d) => ({ key: d.domain_id, name: d.name })), { key: UNASSIGNED, name: "No evidence" }].filter(
    (c) => data.identities.some((i) => (i.primary_domain ?? UNASSIGNED) === c.key),
  );
  const colW = W / Math.max(clusters.length, 1);
  const perCol = clusters.map((c) => data.identities.filter((i) => (i.primary_domain ?? UNASSIGNED) === c.key));
  const rowsNeeded = Math.max(1, ...perCol.map((m) => Math.ceil(m.length / 3)));
  const H = Math.max(360, 140 + rowsNeeded * 140);
  const nodes: Placed[] = [];
  perCol.forEach((members, ci) => {
    const cols = Math.min(3, members.length);
    members.forEach((id, k) => {
      const row = Math.floor(k / 3);
      const inRow = Math.min(cols, members.length - row * 3);
      const cx = colW * ci + colW / 2 + (k % 3 - (inRow - 1) / 2) * 130;
      const cy = 130 + row * 140 + (k % 2 ? 28 : 0);
      nodes.push({ id, x: cx, y: cy, r: 12 + Math.min(id.skill_count, 8) * 7 });
    });
  });
  return { clusters, colW, nodes, H };
}

const UNSCORED_PAGE = 60;

function WorkforceBody({ data }: { data: WorkforceData }) {
  const { label } = useNames();
  const scored = data.identities.filter((i) => i.skill_count > 0);
  const unscored = data.identities.filter((i) => i.skill_count === 0);
  const [selected, setSelected] = useState<string>((scored[0] ?? data.identities[0]).coded_identity);
  const [filter, setFilter] = useState("");
  const { clusters, colW, nodes, H } = useMemo(() => layout(data), [data]);
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
        <div className="canvas">
          <svg viewBox={`0 0 ${W} ${H}`} role="group" aria-label="Workforce topology">
            {clusters.map((c, i) => (
              <g key={c.key}>
                {i > 0 && <line x1={colW * i} x2={colW * i} y1={24} y2={H - 24} stroke="#E5E7EB" strokeDasharray="3 5" />}
                <text className="cluster-label" x={colW * i + colW / 2} y={48} textAnchor="middle">
                  {c.name}
                </text>
              </g>
            ))}
            {nodes.map(({ id, x, y, r }) => {
              const active = id.coded_identity === current.coded_identity;
              const ringR = r + 6;
              const circ = 2 * Math.PI * ringR;
              const conf = id.mean_confidence ?? 0;
              return (
                <g
                  key={id.coded_identity}
                  className="node"
                  role="button"
                  tabIndex={0}
                  aria-pressed={active}
                  aria-label={`${id.coded_identity}, ${id.skill_count} skills`}
                  onClick={() => setSelected(id.coded_identity)}
                  onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), setSelected(id.coded_identity))}
                >
                  <circle cx={x} cy={y} r={ringR} fill="none" stroke="#E5E7EB" strokeWidth={3} />
                  <circle
                    cx={x}
                    cy={y}
                    r={ringR}
                    fill="none"
                    stroke={active ? "#B5122B" : "#004A5D"}
                    strokeWidth={3}
                    strokeDasharray={`${circ * conf} ${circ}`}
                    transform={`rotate(-90 ${x} ${y})`}
                  />
                  <circle
                    className="node-core"
                    cx={x}
                    cy={y}
                    r={r}
                    fill={active ? "#FFF1F2" : "#FFFFFF"}
                    stroke={active ? "#B5122B" : "#CBD5E1"}
                    strokeWidth={1.5}
                  />
                  <text x={x} y={y} textAnchor="middle" dominantBaseline="central" fontSize={12} fontWeight={600} fill="#0F172A">
                    {id.skill_count}
                  </text>
                  <text className="node-label" x={x} y={y + ringR + 16} textAnchor="middle">
                    {label(id.coded_identity)}
                  </text>
                </g>
              );
            })}
          </svg>
          <div className="canvas-legend">
            <span>Node size = skill breadth (records)</span>
            <span>Ring = mean confidence</span>
            <span>
              {int(scored.length)} scored of {int(data.identities.length)} coded identities
            </span>
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
