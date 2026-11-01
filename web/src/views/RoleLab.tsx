import { AnimatePresence, motion } from "framer-motion";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { managerToolsApi, skillsApi } from "../api/endpoints";
import type { FitnessResult, RoleProfile, SkillSummaryRow } from "../api/types";
import { pct } from "../lib/format";
import { PersonName } from "../lib/names";
import { useApi, useStale } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { useCalm, useToasts } from "../ui/Fx";
import { IconClose, IconPlus } from "../ui/Icons";
import { ErrorState, InlineError, Loading } from "../ui/States";

type Row = { skill_id: string; level: number; critical: boolean };
const fromRole = (r: RoleProfile): Row[] =>
  Object.entries(r.required_skills).map(([skill_id, level]) => ({ skill_id, level, critical: r.critical_skills.includes(skill_id) }));

export default function RoleLab() {
  const [tick, setTick] = useState(0);
  const q = useApi(
    async (s) => {
      const [skills, roles] = await Promise.all([skillsApi.list(s), skillsApi.roles(s)]);
      return { skills: skills.skills, roles: roles.roles };
    },
    [tick],
  );
  const data = useStale(q);
  return (
    <>
      <PageHead
        trail={["Role lab"]}
        title="Role lab"
        lede="Change what a role needs and watch the shortlist move. Nothing here is saved or ranked until you say so."
      />
      {q.status === "loading" && !data && <Loading label="Loading roles" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data && data.roles.length === 0 && <ErrorState error={new Error("No role profiles exist yet.")} />}
      {data && data.roles.length > 0 && <Lab skills={data.skills} roles={data.roles} reloadRoles={() => setTick((n) => n + 1)} />}
    </>
  );
}

function Lab({ skills, roles, reloadRoles }: { skills: SkillSummaryRow[]; roles: RoleProfile[]; reloadRoles: () => void }) {
  const calm = useCalm();
  const { push, host } = useToasts();
  const [roleId, setRoleId] = useState(roles[0].role_id);
  const role = roles.find((r) => r.role_id === roleId) ?? roles[0];
  const [rows, setRows] = useState<Row[]>(fromRole(role));
  const [minCoverage, setMinCoverage] = useState(role.min_coverage_ratio);
  const [result, setResult] = useState<FitnessResult | null>(null);
  const [baseline, setBaseline] = useState<string[] | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const used = new Set(rows.map((r) => r.skill_id));
  const skillName = (id: string) => skills.find((s) => s.skill_id === id)?.name ?? id;
  const custom = roles.filter((r) => r.role_id.startsWith("custom_"));

  const pick = (id: string) => {
    const r = roles.find((x) => x.role_id === id);
    if (!r) return;
    setRoleId(id);
    setRows(fromRole(r));
    setMinCoverage(r.min_coverage_ratio);
    setBaseline(null);
  };
  const update = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));

  const body = useMemo(
    () => ({
      request_id: "role-lab",
      required_skills: Object.fromEntries(rows.map((r) => [r.skill_id, r.level])),
      critical_skills: rows.filter((r) => r.critical).map((r) => r.skill_id),
      min_coverage_ratio: minCoverage,
      shortlist_size: 6,
    }),
    [rows, minCoverage],
  );

  // The shortlist for the role exactly as saved: what "moved" is measured against.
  useEffect(() => {
    const c = new AbortController();
    managerToolsApi
      .preview(
        {
          request_id: "role-lab-base",
          required_skills: role.required_skills,
          critical_skills: role.critical_skills,
          min_coverage_ratio: role.min_coverage_ratio,
          shortlist_size: 6,
        },
        c.signal,
      )
      .then((r) => setBaseline(r.candidates.map((x) => x.coded_identity)))
      .catch(() => undefined);
    return () => c.abort();
  }, [role]);

  // Live preview, debounced so dragging a level does not hammer the server.
  const seq = useRef(0);
  useEffect(() => {
    const mine = ++seq.current;
    const c = new AbortController();
    const t = setTimeout(
      () => {
        managerToolsApi.preview(body, c.signal).then(
          (r) => {
            if (mine === seq.current) {
              setResult(r);
              setError(null);
            }
          },
          (e: Error) => e.name !== "AbortError" && mine === seq.current && setError(e),
        );
      },
      import.meta.env.MODE === "test" ? 0 : 350,
    );
    return () => {
      clearTimeout(t);
      c.abort();
    };
  }, [body]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const made = await managerToolsApi.createRole({
        role_name: name.trim(),
        required_skills: body.required_skills,
        critical_skills: body.critical_skills,
        min_coverage_ratio: Math.max(0.3, Math.min(1, minCoverage)),
      });
      push(`Saved “${made.role_name}”. It now appears in Find people.`, "ok");
      setName("");
      reloadRoles();
    } catch (err) {
      setError(err as Error);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (id: string) => {
    try {
      await managerToolsApi.deleteRole(id);
      push("Role deleted", "info");
      if (id === roleId) pick(roles.find((r) => r.role_id !== id)!.role_id);
      reloadRoles();
    } catch (err) {
      setError(err as Error);
    }
  };

  return (
    <>
      {host}
      <div className="split lab">
        <section className="panel">
          <div className="panel-head">
            <h2>What the role needs</h2>
            <select className="select" style={{ width: "auto" }} aria-label="Start from a role" value={roleId} onChange={(e) => pick(e.target.value)}>
              {roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_name}
                </option>
              ))}
            </select>
          </div>
          <div className="panel-body">
            {rows.map((r, i) => (
              <div className="lab-row" key={r.skill_id}>
                <span className="lab-skill">{skillName(r.skill_id)}</span>
                <input
                  className="lab-slider"
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={r.level}
                  aria-label={`Level for ${skillName(r.skill_id)}`}
                  onChange={(e) => update(i, { level: Number(e.target.value) })}
                />
                <span className="lab-level num">L{r.level}</span>
                <label className="checkbox">
                  <input type="checkbox" checked={r.critical} aria-label={`${skillName(r.skill_id)} is critical`} onChange={(e) => update(i, { critical: e.target.checked })} />
                  Critical
                </label>
                <button type="button" className="icon-btn" aria-label={`Remove ${skillName(r.skill_id)}`} disabled={rows.length === 1} onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))}>
                  <IconClose />
                </button>
              </div>
            ))}
            <div className="lab-add">
              <select
                className="select"
                aria-label="Add a skill"
                value=""
                disabled={rows.length >= 12}
                onChange={(e) => e.target.value && setRows((rs) => [...rs, { skill_id: e.target.value, level: 3, critical: false }])}
              >
                <option value="">Add a skill…</option>
                {skills.filter((s) => !used.has(s.skill_id)).map((s) => (
                  <option key={s.skill_id} value={s.skill_id}>
                    {s.name}
                  </option>
                ))}
              </select>
              <IconPlus width={14} height={14} />
            </div>
            <label className="field" style={{ marginTop: 16 }}>
              <span className="label">Minimum coverage: {Math.round(minCoverage * 100)}% of required skills</span>
              <input className="lab-slider wide" type="range" min={0.3} max={1} step={0.05} value={minCoverage} aria-label="Minimum coverage" onChange={(e) => setMinCoverage(Number(e.target.value))} />
            </label>

            <form className="lab-save" onSubmit={save}>
              <input className="input" aria-label="Name for this role" placeholder="Name this role to keep it" value={name} minLength={3} maxLength={80} onChange={(e) => setName(e.target.value)} />
              <button className="btn btn-primary btn-sm" type="submit" disabled={saving || name.trim().length < 3}>
                {saving ? "Saving…" : "Save as a role"}
              </button>
            </form>
            {custom.length > 0 && (
              <div className="lab-custom">
                <span className="label">Your saved roles</span>
                {custom.map((r) => (
                  <div className="lab-custom-row" key={r.role_id}>
                    <button className="link-btn" onClick={() => pick(r.role_id)}>
                      {r.role_name}
                    </button>
                    <button className="btn btn-ghost btn-sm" aria-label={`Delete ${r.role_name}`} onClick={() => remove(r.role_id)}>
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Who would fit</h2>
            <span className="chip chip-teal">Live preview</span>
          </div>
          <div className="panel-body">
            <InlineError error={error} />
            {!result && !error && <Loading label="Ranking" rows={3} />}
            {result && (
              <>
                {result.candidates.length === 0 ? (
                  <p className="ink-2" role="status" style={{ margin: 0 }}>
                    No one fits this version of the role. Lower a level, drop a critical flag, or reduce coverage to see who comes into range.
                  </p>
                ) : (
                  <ol className="lab-results" aria-label="Preview shortlist">
                    <AnimatePresence initial={false}>
                      {result.candidates.map((c, i) => {
                        const before = baseline ? baseline.indexOf(c.coded_identity) : -2;
                        const delta = before >= 0 ? before - i : null;
                        return (
                          <motion.li key={c.coded_identity} layout={!calm} initial={calm ? false : { opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ type: "spring", stiffness: 420, damping: 34 }}>
                            <span className="lab-rank num">{i + 1}</span>
                            <div className="lab-who">
                              <PersonName coded={c.coded_identity} />
                              <div className="lab-bar">
                                <motion.span initial={calm ? false : { width: 0 }} animate={{ width: `${Math.max(2, c.fitness_score * 100)}%` }} transition={{ duration: 0.5 }} />
                              </div>
                            </div>
                            <span className="num lab-score">{pct(c.fitness_score)}</span>
                            <span className={`lab-move ${delta === null ? "new" : delta > 0 ? "up" : delta < 0 ? "down" : ""}`}>
                              {delta === null ? (before === -2 ? "" : "new") : delta > 0 ? `▲ ${delta}` : delta < 0 ? `▼ ${-delta}` : "–"}
                            </span>
                          </motion.li>
                        );
                      })}
                    </AnimatePresence>
                  </ol>
                )}
                {result.excluded_candidates.length > 0 && (
                  <p className="hint" style={{ marginTop: 12 }}>
                    {result.excluded_candidates.length} {result.excluded_candidates.length === 1 ? "person is" : "people are"} left out: no proof on a critical skill, or too few of the required skills.
                  </p>
                )}
                <p className="hint">This is a preview from the same engine as Find people. Nothing is stored, audited or recorded as a request.</p>
              </>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
