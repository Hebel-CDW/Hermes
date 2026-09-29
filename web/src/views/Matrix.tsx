import { motion } from "framer-motion";
import { useState } from "react";
import { Link } from "react-router-dom";
import { ApiError } from "../api/http";
import { dataQualityApi, matrixApi, skillsApi, workforceApi } from "../api/endpoints";
import type { SurveyMatrix } from "../api/types";
import { int, pct } from "../lib/format";
import { useNames } from "../lib/names";
import { useApi } from "../lib/useApi";
import { useMotionSafe } from "../motion/PageMotion";
import { PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, Loading } from "../ui/States";

const LEGEND: [string, string][] = [
  ["l0", "No evidence"],
  ["l1", "1 Awareness"],
  ["l2", "2 Working"],
  ["l3", "3 Proficient"],
  ["l4", "4 Advanced"],
  ["l5", "5 Expert"],
];

const EMPTY_SURVEY: SurveyMatrix = {
  kind: "survey_2025",
  used_for_fitness: false,
  label: "2025 manager survey — not used for Find people",
  cells: [],
};

export default function Matrix() {
  const { label } = useNames();
  const { fadeOnly } = useMotionSafe();
  const [mode, setMode] = useState<"living" | "survey">("living");
  const [focus, setFocus] = useState<string | null>(null);
  const q = useApi(
    async (s) => {
      const [dashboard, skills, workforce, dq] = await Promise.all([
        matrixApi.dashboard(s),
        skillsApi.list(s),
        workforceApi.get(s),
        dataQualityApi.get(s),
      ]);
      let survey = EMPTY_SURVEY;
      try {
        survey = await matrixApi.survey(s);
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
      }
      return { dashboard, skills: skills.skills, workforce, dq, survey };
    },
    [],
  );

  const toggle = (
    <div className="seg" role="group" aria-label="Matrix source">
      <button
        type="button"
        className={`btn btn-sm ${mode === "living" ? "btn-primary" : ""}`}
        aria-pressed={mode === "living"}
        data-testid="matrix-mode-living"
        onClick={() => {
          setMode("living");
          setFocus(null);
        }}
      >
        Living (evidence)
      </button>
      <button
        type="button"
        className={`btn btn-sm ${mode === "survey" ? "btn-primary" : ""}`}
        aria-pressed={mode === "survey"}
        data-testid="matrix-mode-survey"
        onClick={() => {
          setMode("survey");
          setFocus(null);
        }}
      >
        2025 survey
      </button>
      <Link className="btn btn-sm" to="/update-skills">
        Update skills
      </Link>
    </div>
  );

  return (
    <>
      <PageHead
        trail={["Team skills"]}
        title="Team skills"
        lede={
          mode === "survey"
            ? "2025 manager survey — labelled comparison only. Not used for Find people."
            : "Who is strong at what, based on real work. Darker means stronger."
        }
        aside={toggle}
      />
      {q.status === "loading" && <Loading label="Loading matrix" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (() => {
          const { dashboard, skills, workforce, dq, survey } = q.data;
          if (mode === "survey") {
            const names = new Map(skills.map((s) => [s.skill_id, s.name]));
            const skillIds = [...new Set(survey.cells.map((c) => c.skill_id))];
            const columns = [...new Set(survey.cells.map((c) => c.coded_identity))];
            if (skillIds.length === 0 || columns.length === 0) {
              return (
                <EmptyState title="No mapped 2025 survey cells">
                  {survey.label}. Unmapped workbook labels stay out of this view and out of scoring.
                </EmptyState>
              );
            }
            const cells = new Map(survey.cells.map((c) => [`${c.skill_id}|${c.coded_identity}`, c]));
            const focused = focus ? cells.get(focus) : undefined;
            return (
              <>
                <p className="hint" data-testid="survey-disclaimer">
                  {survey.label}. Find people ranks the living evidence matrix only.
                </p>
                <div className="panel">
                  <div className="panel-head">
                    <div className="legend" aria-label="Proficiency legend">
                      {LEGEND.map(([cls, legendLabel]) => (
                        <span key={cls}>
                          <span className={`swatch cell ${cls}`} style={{ width: 14, height: 14 }} />
                          {legendLabel}
                        </span>
                      ))}
                    </div>
                    <span className="muted" style={{ fontSize: 12 }}>
                      {survey.cells.length} survey cells
                    </span>
                  </div>
                  <div className="panel-body table-wrap">
                    <table className="heatmap" aria-label="2025 survey matrix">
                      <thead>
                        <tr>
                          <th scope="col">
                            <span className="sr-only">Skill</span>
                          </th>
                          {columns.map((c) => (
                            <th key={c} scope="col">
                              <span className="person-col">{label(c)}</span>
                              {label(c) !== c && <span className="person-token">{c}</span>}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {skillIds.map((skillId) => (
                          <tr key={skillId}>
                            <th scope="row" title={skillId}>
                              {names.get(skillId) ?? skillId}
                            </th>
                            {columns.map((c, colIndex) => {
                              const key = `${skillId}|${c}`;
                              const r = cells.get(key);
                              const name = label(c);
                              return (
                                <motion.td
                                  key={c}
                                  className={`cell ${r ? `l${r.level}` : "l0"} ${focus === key ? "focused" : ""}`}
                                  data-testid={`survey-cell-${skillId}-${c}`}
                                  {...fadeOnly(Math.min(colIndex * 0.03, 0.24))}
                                >
                                  {r ? (
                                    <button
                                      onClick={() => setFocus(key)}
                                      onMouseEnter={() => setFocus(key)}
                                      onFocus={() => setFocus(key)}
                                      aria-label={`${names.get(skillId) ?? skillId}, ${name}: survey level ${r.level}`}
                                    >
                                      {r.level}
                                    </button>
                                  ) : (
                                    <span aria-label={`${names.get(skillId) ?? skillId}, ${name}: no survey cell`}>·</span>
                                  )}
                                </motion.td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="panel section" aria-live="polite">
                  <div className="panel-body">
                    {focused ? (
                      <div>
                        <div className="label">Survey cell (not scored)</div>
                        <div>
                          {label(focused.coded_identity)} · {names.get(focused.skill_id) ?? focused.skill_id} · level{" "}
                          {focused.level}
                        </div>
                      </div>
                    ) : (
                      <span className="muted">Survey ratings are a labelled comparison. They never enter Find people.</span>
                    )}
                  </div>
                </div>
              </>
            );
          }
          if (dashboard.skill_distribution.length === 0) {
            const real = dq.data_classification === "real";
            return (
              <div className="state empty" data-testid="matrix-unavailable">
                <h3>{real ? "Real capability matrix unavailable" : "Capability matrix unavailable"}</h3>
                <p>Skill labels require governed mapping before scoring.</p>
                <div className="chips" style={{ marginTop: 6 }}>
                  <span className="chip chip-crimson" data-testid="matrix-pending">
                    {dq.pipeline.pending === null ? "No workbook ingestion" : `${int(dq.pipeline.pending)} pending mappings`}
                  </span>
                  <span className="chip">{int(dq.pipeline.mapped ?? 0)} mapped</span>
                  <span className="chip">{int(dq.pipeline.scored)} scored identities</span>
                  <span className="chip">{int(dq.pipeline.imported)} coded identities imported</span>
                </div>
              </div>
            );
          }
          const columns = [...new Set([...workforce.identities.map((i) => i.coded_identity), ...dashboard.skill_distribution.map((r) => r.coded_identity)])];
          if (columns.length === 0 || skills.length === 0) {
            return <EmptyState title="Matrix is empty">No people or governed skills are available.</EmptyState>;
          }
          const cells = new Map(dashboard.skill_distribution.map((r) => [`${r.skill_id}|${r.coded_identity}`, r]));
          const focused = focus ? cells.get(focus) : undefined;
          return (
            <>
              <div className="panel">
                <div className="panel-head">
                  <div className="legend" aria-label="Proficiency legend">
                    {LEGEND.map(([cls, legendLabel]) => (
                      <span key={cls}>
                        <span className={`swatch cell ${cls}`} style={{ width: 14, height: 14 }} />
                        {legendLabel}
                      </span>
                    ))}
                  </div>
                  <span className="muted" style={{ fontSize: 12 }}>
                    {dashboard.skill_distribution.length} evidence cells
                  </span>
                </div>
                <div className="panel-body table-wrap">
                  <table className="heatmap" aria-label="Skill matrix">
                    <thead>
                      <tr>
                        <th scope="col">
                          <span className="sr-only">Skill</span>
                        </th>
                        {columns.map((c) => (
                          <th key={c} scope="col">
                            <span className="person-col">{label(c)}</span>
                            {label(c) !== c && <span className="person-token">{c}</span>}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {skills.map((s) => (
                        <tr key={s.skill_id}>
                          <th scope="row" title={s.skill_id}>
                            {s.name}
                          </th>
                          {columns.map((c, colIndex) => {
                            const key = `${s.skill_id}|${c}`;
                            const r = cells.get(key);
                            const name = label(c);
                            return (
                              <motion.td
                                key={c}
                                className={`cell ${r ? `l${r.proficiency}` : "l0"} ${focus === key ? "focused" : ""}`}
                                data-testid={`cell-${s.skill_id}-${c}`}
                                {...fadeOnly(Math.min(colIndex * 0.03, 0.24))}
                              >
                                {r ? (
                                  <button
                                    onClick={() => setFocus(key)}
                                    onMouseEnter={() => setFocus(key)}
                                    onFocus={() => setFocus(key)}
                                    aria-label={`${s.name}, ${name}: level ${r.proficiency}`}
                                  >
                                    {r.proficiency}
                                  </button>
                                ) : (
                                  <span aria-label={`${s.name}, ${name}: no evidence`}>·</span>
                                )}
                              </motion.td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
              <div className="panel section" aria-live="polite">
                <div className="panel-body">
                  {focused ? (
                    <div className="grid cols-3" style={{ alignItems: "center" }}>
                      <div>
                        <div className="label">Cell</div>
                        <div>
                          <span>{label(focused.coded_identity)}</span>
                          {label(focused.coded_identity) !== focused.coded_identity && (
                            <span className="mono muted" style={{ marginLeft: 8 }}>
                              {focused.coded_identity}
                            </span>
                          )}
                          <span> · {skills.find((s) => s.skill_id === focused.skill_id)?.name ?? focused.skill_id}</span>
                        </div>
                      </div>
                      <div>
                        <div className="label">Level</div>
                        <div className="num">{focused.proficiency}</div>
                      </div>
                      <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                        <span>
                          <span className="label">Confidence</span> <span className="num">{pct(focused.confidence)}</span>
                        </span>
                        <span>
                          <span className="label">Freshness</span> <span className="num">{pct(focused.freshness)}</span>
                        </span>
                        <span>
                          <span className="label">Volume</span> <span className="num">{pct(focused.volume_score)}</span>
                        </span>
                      </div>
                    </div>
                  ) : (
                    <span className="muted">Click a cell to see how strong and how recent the evidence is.</span>
                  )}
                  <div style={{ marginTop: 12, display: "flex", gap: 8, flexWrap: "wrap" }}>
                    {focused && (
                      <Link className="btn btn-sm" to={`/update-skills?person=${encodeURIComponent(focused.coded_identity)}`}>
                        Update this person
                      </Link>
                    )}
                    <Link className="btn btn-sm" to="/learning">
                      Next: Learning
                    </Link>
                  </div>
                </div>
              </div>
            </>
          );
        })()}
    </>
  );
}
