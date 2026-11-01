import { motion } from "framer-motion";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { requestsApi } from "../api/endpoints";
import type { RankedCandidate, RequestDetail } from "../api/types";
import { downloadText, toCsv } from "../lib/csv";
import { pct } from "../lib/format";
import { useNames } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { Radar, Rise, Stagger, useCalm } from "../ui/Fx";
import { IconArrowLeft } from "../ui/Icons";
import { EmptyState, ErrorState, Loading } from "../ui/States";

const COLORS = ["#b5122b", "#004a5d", "#0f6b4f"];
const MAX_PICK = 3;

export default function Compare() {
  const { id = "" } = useParams();
  const q = useApi((s) => requestsApi.get(id, s), [id]);
  return (
    <>
      <Link className="back-link" to={`/requests/${encodeURIComponent(id)}`}>
        <IconArrowLeft /> Back to who fits
      </Link>
      <PageHead trail={["Find people", "Compare"]} title="Compare" lede="Put the shortlist side by side: where each person is strong, and where they fall short." />
      {q.status === "loading" && <Loading label="Loading the shortlist" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (q.data.result.candidates.length < 2 ? (
          <EmptyState title="Not enough people to compare">A comparison needs at least two shortlisted people.</EmptyState>
        ) : (
          <CompareBody data={q.data} />
        ))}
    </>
  );
}

function CompareBody({ data }: { data: RequestDetail }) {
  const { label } = useNames();
  const skillName = useSkillName();
  const calm = useCalm();
  const all = data.result.candidates;
  const [picked, setPicked] = useState<string[]>(all.slice(0, MAX_PICK).map((c) => c.coded_identity));
  const required = data.requirements.required_skills ?? {};
  const skillIds = Object.keys(required);
  const chosen = picked.map((p) => all.find((c) => c.coded_identity === p)).filter((c): c is RankedCandidate => Boolean(c));
  const levelOf = (c: RankedCandidate, s: string) => c.reasoning_detail?.[s]?.actual_level ?? 0;

  const toggle = (coded: string) =>
    setPicked((p) => (p.includes(coded) ? (p.length > 2 ? p.filter((x) => x !== coded) : p) : p.length < MAX_PICK ? [...p, coded] : p));

  const series = useMemo(
    () => chosen.map((c, i) => ({ name: label(c.coded_identity), color: COLORS[i % COLORS.length], values: skillIds.map((s) => levelOf(c, s)) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [picked, label],
  );

  const exportCsv = () =>
    downloadText(
      `compare-${data.request_id}.csv`,
      toCsv([
        ["Skill", "Needs", ...chosen.map((c) => label(c.coded_identity))],
        ...skillIds.map((s) => [skillName(s), required[s], ...chosen.map((c) => levelOf(c, s) || "")]),
        ["Fit", "", ...chosen.map((c) => pct(c.fitness_score))],
      ]),
    );

  const best = (s: string) => Math.max(...chosen.map((c) => levelOf(c, s)));

  return (
    <>
      <section className="panel no-print">
        <div className="panel-body compare-pick">
          <span className="label">Compare up to {MAX_PICK}</span>
          {all.map((c) => (
            <button key={c.coded_identity} className={`pill ${picked.includes(c.coded_identity) ? "on" : ""}`} aria-pressed={picked.includes(c.coded_identity)} onClick={() => toggle(c.coded_identity)}>
              #{c.rank} {label(c.coded_identity)}
            </button>
          ))}
          <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
            <button className="btn btn-sm" onClick={exportCsv}>
              Download CSV
            </button>
            <button className="btn btn-sm" onClick={() => window.print()}>
              Print or save as PDF
            </button>
          </div>
        </div>
      </section>

      <div className="grid cols-2" style={{ marginTop: 16 }}>
        <section className="panel">
          <div className="panel-head">
            <h2>Shape of each person</h2>
            <span className="muted">Dashed line is what the role needs</span>
          </div>
          <div className="panel-body">
            <Radar axes={skillIds.map(skillName)} series={series} required={skillIds.map((s) => required[s])} />
            <ul className="legend">
              {series.map((s) => (
                <li key={s.name}>
                  <i style={{ background: s.color }} /> {s.name}
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Fit</h2>
          </div>
          <Stagger className="panel-body fit-bars">
            {chosen.map((c, i) => (
              <Rise key={c.coded_identity}>
                <div className="fit-row">
                  <div className="fit-name">
                    <strong>{label(c.coded_identity)}</strong>
                    <span className="num">{pct(c.fitness_score)}</span>
                  </div>
                  <div className="lab-bar big">
                    <motion.span
                      style={{ background: COLORS[i % COLORS.length] }}
                      initial={calm ? false : { width: 0 }}
                      animate={{ width: `${Math.max(2, c.fitness_score * 100)}%` }}
                      transition={{ duration: 0.7, delay: calm ? 0 : i * 0.12 }}
                    />
                  </div>
                  <span className="muted">
                    Rank {c.rank} · evidence for {c.calculation?.matched_skill_count ?? "—"} of {c.calculation?.required_skill_count ?? skillIds.length} skills
                  </span>
                </div>
              </Rise>
            ))}
          </Stagger>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 16 }}>
        <div className="panel-head">
          <h2>Skill by skill</h2>
        </div>
        <div className="table-wrap">
          <table className="data" aria-label="Skill by skill comparison">
            <thead>
              <tr>
                <th>Skill</th>
                <th>Role needs</th>
                {chosen.map((c, i) => (
                  <th key={c.coded_identity}>
                    <span className="dot-key" style={{ background: COLORS[i % COLORS.length] }} /> {label(c.coded_identity)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {skillIds.map((s) => (
                <tr key={s}>
                  <td>{skillName(s)}</td>
                  <td className="num">L{required[s]}</td>
                  {chosen.map((c) => {
                    const lv = levelOf(c, s);
                    const d = c.reasoning_detail?.[s];
                    return (
                      <td key={c.coded_identity} className={lv && lv === best(s) ? "best-cell" : ""}>
                        {lv ? <strong className="num">L{lv}</strong> : <span className="muted">no proof</span>}
                        {d?.status === "adjacent" && <span className="chip" style={{ marginLeft: 6 }}>related skill</span>}
                        {d?.freshness != null && lv > 0 && <div className="muted">{pct(d.freshness, 0)} fresh</div>}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
