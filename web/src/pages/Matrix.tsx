import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { api, Dashboard, MatrixRunRecord } from "../api/client";
import { CoverageRing } from "../components/CoverageRing";
import { NarrateBanner } from "../components/NarrateBanner";
import { SkillHeatmap } from "../components/SkillHeatmap";
import { itemUp, pageVariants, stagger } from "../motion/presets";

type Mode = "live" | string;

function toHeatmapRows(records: MatrixRunRecord[]) {
  return records.map((r) => ({
    coded_identity: String(r.coded_identity),
    skill_id: String(r.skill_id),
    proficiency: Number(r.proficiency),
    freshness: Number(r.freshness ?? 0),
  }));
}

export function Matrix() {
  const reduced = useReducedMotion();
  const [data, setData] = useState<Dashboard | null>(null);
  const [runs, setRuns] = useState<string[]>([]);
  const [mode, setMode] = useState<Mode>("live");
  const [runRows, setRunRows] = useState<MatrixRunRecord[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scrubBusy, setScrubBusy] = useState(false);

  useEffect(() => {
    Promise.all([api.dashboard(), api.matrixRuns()])
      .then(([dash, runList]) => {
        setData(dash);
        setRuns(runList.runs);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load matrix"));
  }, []);

  async function selectMode(next: Mode) {
    setMode(next);
    setError(null);
    if (next === "live") {
      setRunRows(null);
      return;
    }
    setScrubBusy(true);
    try {
      const res = await api.matrixRun(next);
      setRunRows(res.records);
    } catch (err) {
      setRunRows(null);
      setError(err instanceof Error ? err.message : "Failed to load run");
    } finally {
      setScrubBusy(false);
    }
  }

  const freshness = data ? Object.entries(data.avg_freshness_by_skill) : [];
  const heatmapRows = useMemo(() => {
    if (mode !== "live" && runRows) return toHeatmapRows(runRows);
    return data?.skill_distribution ?? [];
  }, [mode, runRows, data]);

  const scrubIndex = mode === "live" ? -1 : Math.max(0, runs.indexOf(mode));

  return (
    <motion.div className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="panel">
        <h2 className="h2">Matrix</h2>
        <p className="lede">Evidence coverage, freshness, and skill distribution — coded identities only.</p>
        <NarrateBanner>Real names never appear on this view. Resolution is shortlist-only and audited.</NarrateBanner>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {!data && !error ? <p className="empty">Loading matrix…</p> : null}

        {data ? (
          <motion.div variants={stagger} initial="initial" animate="animate">
            <motion.div
              variants={itemUp}
              style={{
                marginBottom: "1.75rem",
                padding: "1rem 1.1rem",
                border: "1px solid var(--line)",
                borderRadius: "var(--radius)",
                background: "rgba(232,238,244,0.03)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontSize: 12, letterSpacing: "0.08em", color: "var(--ink-muted)" }}>
                    TIME SCRUBBER
                  </div>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: "1.15rem", marginTop: 4 }}>
                    {mode === "live" ? "Live matrix" : `Run ${mode.slice(0, 12)}…`}
                  </div>
                </div>
                <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>
                  {runs.length} historical run{runs.length === 1 ? "" : "s"}
                  {scrubBusy ? " · loading…" : ""}
                </div>
              </div>
              <div className="field" style={{ marginTop: "0.85rem" }}>
                <label htmlFor="scrub">As-of run</label>
                <input
                  id="scrub"
                  type="range"
                  min={-1}
                  max={Math.max(-1, runs.length - 1)}
                  step={1}
                  value={scrubIndex}
                  disabled={!runs.length && mode === "live"}
                  onChange={(e) => {
                    const idx = Number(e.target.value);
                    if (idx < 0) selectMode("live");
                    else selectMode(runs[idx]);
                  }}
                />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--ink-muted)" }}>
                  <span>Live</span>
                  <span>{runs.length ? "Oldest→newest scrub" : "No runs yet"}</span>
                </div>
              </div>
              {runs.length ? (
                <select
                  aria-label="Select computation run"
                  value={mode}
                  onChange={(e) => selectMode(e.target.value)}
                  style={{
                    marginTop: "0.65rem",
                    width: "100%",
                    background: "var(--bg-2)",
                    border: "1px solid var(--line)",
                    borderRadius: "var(--radius)",
                    color: "var(--ink)",
                    padding: "0.55rem 0.75rem",
                  }}
                >
                  <option value="live">Live (current)</option>
                  {runs.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              ) : null}
            </motion.div>

            {mode === "live" ? (
              <motion.div
                variants={itemUp}
                style={{ display: "flex", gap: "2rem", flexWrap: "wrap", alignItems: "center", marginBottom: "2rem" }}
              >
                <CoverageRing pct={data.coverage.coverage_pct} />
                <div>
                  <div style={{ fontSize: 14, color: "var(--ink-muted)" }}>Pilot population</div>
                  <div style={{ fontFamily: "var(--font-display)", fontSize: "2rem", fontWeight: 700 }}>
                    {data.coverage.with_demonstrated}/{data.coverage.pilot_size}
                  </div>
                  <div style={{ color: "var(--ink-muted)", fontSize: 14 }}>with demonstrated evidence</div>
                </div>
              </motion.div>
            ) : (
              <motion.p
                variants={itemUp}
                style={{ color: "var(--ink-muted)", marginBottom: "1.5rem" }}
                initial={reduced ? false : undefined}
              >
                Historical snapshot — coverage ring is live-only. Heatmap shows skills as of this computation run.
              </motion.p>
            )}

            {mode === "live" ? (
              <motion.div variants={itemUp} style={{ marginBottom: "2.5rem" }}>
                <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 1rem" }}>Freshness by skill</h3>
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {freshness.map(([skill, val]) => (
                    <li key={skill} style={{ marginBottom: "0.85rem" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 14, marginBottom: 4 }}>
                        <span>{skill}</span>
                        <span style={{ color: "var(--teal)" }}>{val.toFixed(2)}</span>
                      </div>
                      <div style={{ height: 8, borderRadius: 999, background: "rgba(232,238,244,0.08)", overflow: "hidden" }}>
                        <motion.div
                          initial={reduced ? false : { width: 0 }}
                          animate={{ width: `${val * 100}%` }}
                          transition={{ duration: reduced ? 0.01 : 0.8, ease: [0.22, 1, 0.36, 1] }}
                          style={{ height: "100%", background: "var(--teal)" }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
              </motion.div>
            ) : null}

            <motion.div variants={itemUp}>
              <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 1rem" }}>
                Skill distribution {mode === "live" ? "(live)" : "(as-of run)"}
              </h3>
              {heatmapRows.length ? (
                <SkillHeatmap rows={heatmapRows} />
              ) : (
                <p className="empty">No matrix rows for this selection.</p>
              )}
            </motion.div>
          </motion.div>
        ) : null}
      </div>
    </motion.div>
  );
}
