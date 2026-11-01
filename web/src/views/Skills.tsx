import { useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { dataQualityApi, skillsApi } from "../api/endpoints";
import type { SkillSummaryRow } from "../api/types";
import { int, pct } from "../lib/format";
import { useApi } from "../lib/useApi";
import { Bar, Levels, Metric, PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, Loading } from "../ui/States";

export default function Skills() {
  const list = useApi((s) => skillsApi.list(s), []);
  const [params, setParams] = useSearchParams();
  const skills = list.status === "success" ? list.data.skills : [];
  const selected = params.get("skill") ?? skills[0]?.skill_id ?? null;
  const select = (id: string) => setParams({ skill: id }, { replace: true });

  return (
    <>
      <PageHead
        trail={["Skills", "Approved list"]}
        title="Skills atlas"
        lede="Every skill Hermes knows about and how they relate. Pick one to see who has it."
      />
      {list.status === "loading" && <Loading label="Loading skills" />}
      {list.status === "error" && <ErrorState error={list.error} onRetry={list.reload} />}
      {list.status === "success" &&
        (skills.length === 0 ? (
          <EmptyState title="No governed skills">The taxonomy defines no skills.</EmptyState>
        ) : (
          <div className="split">
            <div style={{ minWidth: 0 }}>
              <Atlas skills={skills} selected={selected} onSelect={select} />
              <WorkbookLabels canonical={skills.length} />
            </div>
            {selected && <SkillInspector key={selected} skillId={selected} onSelect={select} />}
          </div>
        ))}
    </>
  );
}

function Atlas({ skills, selected, onSelect }: { skills: SkillSummaryRow[]; selected: string | null; onSelect: (id: string) => void }) {
  const domains = useMemo(() => {
    const byDomain = new Map<string, { id: string; name: string; members: SkillSummaryRow[] }>();
    for (const s of skills) {
      if (!byDomain.has(s.domain_id)) byDomain.set(s.domain_id, { id: s.domain_id, name: s.domain_name, members: [] });
      byDomain.get(s.domain_id)!.members.push(s);
    }
    return [...byDomain.values()];
  }, [skills]);
  const current = skills.find((s) => s.skill_id === selected);
  const related = new Set<string>([
    ...(current?.relations ?? []),
    ...skills.filter((s) => selected && s.relations.includes(selected)).map((s) => s.skill_id),
  ]);

  return (
    <div className="atlas" role="group" aria-label="Skill topology">
      <div className="atlas-grid">
        {domains.map((d) => (
          <section key={d.id} className="atlas-domain" aria-label={d.name}>
            <h3>
              {d.name} <span className="muted num">{d.members.length}</span>
            </h3>
            <div className="atlas-skills">
              {d.members.map((s) => {
                const active = s.skill_id === selected;
                return (
                  <button
                    key={s.skill_id}
                    type="button"
                    className={`atlas-skill${active ? " is-active" : ""}${related.has(s.skill_id) ? " is-related" : ""}`}
                    aria-pressed={active}
                    aria-label={s.name}
                    onClick={() => onSelect(s.skill_id)}
                  >
                    {s.name}
                  </button>
                );
              })}
            </div>
          </section>
        ))}
      </div>
      <div className="canvas-legend">
        <span>{int(skills.length)} governed skills</span>
        <span>
          <i className="atlas-key is-active" /> Selected
        </span>
        <span>
          <i className="atlas-key is-related" /> Related (adjacent) skills
        </span>
      </div>
    </div>
  );
}

function SkillInspector({ skillId, onSelect }: { skillId: string; onSelect: (id: string) => void }) {
  const q = useApi((s) => skillsApi.get(skillId, s), [skillId]);
  if (q.status === "loading") return <Loading label="Loading skill" />;
  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  const d = q.data;
  const maxCount = Math.max(1, ...Object.values(d.level_distribution));
  return (
    <aside className="panel" aria-label="Skill inspector">
      <div className="panel-head">
        <span className="label">Active node inspection</span>
        <span className="chip chip-teal">{d.domain_name}</span>
      </div>
      <div className="panel-body">
        <h2 style={{ margin: 0, fontSize: 20, letterSpacing: "-0.01em" }} data-testid="skill-name">
          {d.name}
        </h2>
        <div className="mono muted" style={{ fontSize: 12 }}>
          {d.skill_id}
        </div>
        <p className="ink-2" style={{ margin: "10px 0 18px" }}>
          {d.description}
        </p>
        <dl className="dl" style={{ marginBottom: 18 }}>
          <dt>Holders</dt>
          <dd className="num">
            {int(d.identities_with_evidence)} of {int(d.workforce_size)}
          </dd>
          <dt>Mean level</dt>
          <dd className="num">{d.mean_level ?? "—"}</dd>
          <dt>Decay class</dt>
          <dd>{d.decay_class ?? "—"}</dd>
          <dt>Effective half-life</dt>
          <dd className="num">{d.effective_half_life_days !== null ? `${d.effective_half_life_days} days` : "—"}</dd>
        </dl>
        <Metric label="Workforce coverage" value={d.coverage_ratio} tone="crimson" />
        <Metric label="Mean confidence" value={d.mean_confidence} />
        <Metric label="Mean freshness" value={d.mean_freshness} tone="ink" />

        <div className="label" style={{ margin: "22px 0 8px" }}>
          Level distribution
        </div>
        {["1", "2", "3", "4", "5"].map((lvl) => (
          <div key={lvl} style={{ display: "grid", gridTemplateColumns: "24px 1fr 28px", gap: 10, alignItems: "center", padding: "3px 0" }}>
            <span className="muted num">L{lvl}</span>
            <Bar value={(d.level_distribution[lvl] ?? 0) / maxCount} tone="ink" />
            <span className="num" style={{ textAlign: "right" }}>
              {d.level_distribution[lvl] ?? 0}
            </span>
          </div>
        ))}

        <div className="label" style={{ margin: "22px 0 8px" }}>
          Evidence holders
        </div>
        {d.holders.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No coded identity has evidence for this skill.
          </p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Identity</th>
                  <th>Level</th>
                  <th className="right">Conf.</th>
                </tr>
              </thead>
              <tbody>
                {d.holders.map((h) => (
                  <tr key={h.coded_identity}>
                    <td className="mono">{h.coded_identity}</td>
                    <td>
                      <Levels level={h.proficiency} />
                    </td>
                    <td className="right num">{pct(h.confidence, 0)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="label" style={{ margin: "22px 0 8px" }}>
          Related skills
        </div>
        {d.related_skills.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>
            No governed relations.
          </p>
        ) : (
          d.related_skills.map((r) => (
            <button key={r.skill_id} className="list-btn" onClick={() => onSelect(r.skill_id)}>
              <span>{r.name}</span>
              <span className="muted num">{int(r.identities_with_evidence)} holders</span>
            </button>
          ))
        )}

        <details style={{ marginTop: 18 }}>
          <summary className="label" style={{ cursor: "pointer" }}>
            Proficiency definitions
          </summary>
          <ol style={{ paddingLeft: 18, margin: "10px 0 0" }}>
            {d.proficiency_levels.map((p) => (
              <li key={p.level} style={{ marginBottom: 6 }}>
                <strong>{p.label}</strong> <span className="ink-2">{p.definition}</span>
              </li>
            ))}
          </ol>
        </details>
      </div>
    </aside>
  );
}

/** Canonical skills vs. unmapped workbook labels — counts only; labels live in governance, not the atlas. */
function WorkbookLabels({ canonical }: { canonical: number }) {
  const q = useApi((s) => dataQualityApi.get(s), []);
  if (q.status !== "success" || !q.data.ingestion) return null;
  const labels = q.data.ingestion.labels;
  return (
    <section className="panel section" aria-label="Workbook labels" data-testid="workbook-labels">
      <div className="panel-head">
        <h2>Canonical skills vs workbook labels</h2>
        <Link className="btn btn-sm" to="/data-quality">
          Data quality
        </Link>
      </div>
      <div className="panel-body">
        <div className="chips">
          <span className="chip chip-teal">{int(canonical)} canonical skills</span>
          <span className="chip">{int(labels.skill_labels)} workbook skill labels</span>
          <span className="chip">{int(labels.mapped)} mapped</span>
          <span className="chip chip-crimson">{int(labels.pending)} pending mapping</span>
        </div>
        <p className="hint" style={{ marginBottom: 0 }}>
          The atlas shows only the governed ontology. Workbook labels are not Hermes skills until a mapping is approved.
        </p>
      </div>
    </section>
  );
}
