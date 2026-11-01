import { FormEvent, useState } from "react";
import { StepLoader } from "../ui/Loader";
import { useNavigate } from "react-router-dom";
import { requestsApi, skillsApi } from "../api/endpoints";
import type { RankBody, RoleProfile, SkillSummaryRow } from "../api/types";
import { useApi } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { IconClose, IconPlus } from "../ui/Icons";
import { ErrorState, InlineError, Loading } from "../ui/States";

type Row = { skill_id: string; level: number; critical: boolean };

const newRequestId = () => `req-${new Date().toISOString().slice(0, 19).replace(/[-:T]/g, "")}`;
const DEFAULT_ROLE = "Senior Cloud Engineer";

const fromRole = (role: RoleProfile): Row[] =>
  Object.entries(role.required_skills).map(([skill_id, level]) => ({ skill_id, level, critical: role.critical_skills.includes(skill_id) }));

export default function Capability() {
  const q = useApi(
    async (s) => {
      const [skills, roles] = await Promise.all([skillsApi.list(s), skillsApi.roles(s)]);
      return { skills: skills.skills, roles: roles.roles };
    },
    [],
  );
  return (
    <>
      <PageHead trail={["Find people"]} title="Find people" lede="Pick a role. Hermes ranks who fits from skills they have already shown." />
      {q.status === "loading" && <Loading label="Loading roles" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && <CapabilityForm skills={q.data.skills} roles={q.data.roles} />}
    </>
  );
}

function CapabilityForm({ skills, roles }: { skills: SkillSummaryRow[]; roles: RoleProfile[] }) {
  const navigate = useNavigate();
  const seeded = roles.find((r) => r.role_name === DEFAULT_ROLE);
  const [requestId, setRequestId] = useState(newRequestId);
  const [roleId, setRoleId] = useState(seeded?.role_id ?? "");
  const [rows, setRows] = useState<Row[]>(
    seeded ? fromRole(seeded) : [{ skill_id: skills[0]?.skill_id ?? "", level: 3, critical: false }],
  );
  const [minCoverage, setMinCoverage] = useState(seeded ? String(seeded.min_coverage_ratio) : "");
  const [shortlist, setShortlist] = useState(3);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const applyRole = (id: string) => {
    setRoleId(id);
    const role = roles.find((r) => r.role_id === id);
    if (!role) return;
    setRows(fromRole(role));
    setMinCoverage(String(role.min_coverage_ratio));
  };
  const update = (i: number, patch: Partial<Row>) => setRows((rs) => rs.map((r, k) => (k === i ? { ...r, ...patch } : r)));
  const used = new Set(rows.map((r) => r.skill_id));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    const body: RankBody = {
      request_id: requestId.trim(),
      required_skills: Object.fromEntries(rows.map((r) => [r.skill_id, r.level])),
      critical_skills: rows.filter((r) => r.critical).map((r) => r.skill_id),
      shortlist_size: shortlist,
    };
    if (minCoverage.trim() !== "") body.min_coverage_ratio = Number(minCoverage);
    if (roleId) body.role_id = roleId;
    try {
      const started = Date.now();
      const result = await requestsApi.rank(body);
      // Ranking is near-instant; keep the progress card up long enough to read what Hermes is doing.
      const hold = import.meta.env.MODE === "test" ? 0 : 1300 - (Date.now() - started);
      if (hold > 0) await new Promise((r) => setTimeout(r, hold));
      navigate(`/requests/${encodeURIComponent(result.request_id)}`);
    } catch (err) {
      setError(err as Error);
      setPending(false);
    }
  };

  return (
    <form className="split" onSubmit={submit}>
      {pending && (
        <div className="working-overlay">
          <StepLoader
            title="Finding the best people"
            steps={[
              "Reading everyone's proof of work",
              "Checking each person against the role",
              "Scoring skill by skill",
              "Working out who is ahead, and why",
              "Preparing the explanation",
            ]}
            every={250}
          />
        </div>
      )}
      <section className="panel">
        <div className="panel-head">
          <h2>Who are we looking for?</h2>
          {roles.length > 0 && (
            <select name="role_template" className="select" style={{ width: "auto" }} value={roleId} onChange={(e) => applyRole(e.target.value)} aria-label="Role template">
              <option value="">No role template</option>
              {roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_name}
                </option>
              ))}
            </select>
          )}
        </div>
        <div className="panel-body">
          {roleId ? (
            <p className="ink-2" style={{ margin: "0 0 12px" }}>
              {roles.find((r) => r.role_id === roleId)?.role_name} — Hermes will rank who has shown these skills.
            </p>
          ) : null}
          <details className="disclosure" open={!roleId}>
            <summary>Skills in this role</summary>
          {rows.map((r, i) => (
            <div className="form-row" key={i}>
              <select name={`skill_${i}`} className="select" value={r.skill_id} onChange={(e) => update(i, { skill_id: e.target.value })} aria-label={`Skill ${i + 1}`}>
                {skills.map((s) => (
                  <option key={s.skill_id} value={s.skill_id} disabled={s.skill_id !== r.skill_id && used.has(s.skill_id)}>
                    {s.name}
                  </option>
                ))}
              </select>
              <select name={`level_${i}`} className="select" value={r.level} onChange={(e) => update(i, { level: Number(e.target.value) })} aria-label={`Level for skill ${i + 1}`}>
                {[1, 2, 3, 4, 5].map((l) => (
                  <option key={l} value={l}>
                    Level {l}
                  </option>
                ))}
              </select>
              <label className="checkbox">
                <input name={`critical_${i}`} type="checkbox" checked={r.critical} onChange={(e) => update(i, { critical: e.target.checked })} /> Critical
              </label>
              <button type="button" className="icon-btn" aria-label={`Remove skill ${i + 1}`} disabled={rows.length === 1} onClick={() => setRows((rs) => rs.filter((_, k) => k !== i))}>
                <IconClose />
              </button>
            </div>
          ))}
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ marginTop: 12 }}
            disabled={rows.length >= skills.length}
            onClick={() => {
              const next = skills.find((s) => !used.has(s.skill_id));
              if (next) setRows((rs) => [...rs, { skill_id: next.skill_id, level: 3, critical: false }]);
            }}
          >
            <IconPlus width={14} height={14} /> Add skill
          </button>
          </details>
        </div>
      </section>

      <aside className="panel">
        <div className="panel-head">
          <h2>Find a fit</h2>
        </div>
        <div className="panel-body">
          <div className="field" style={{ marginTop: 4 }}>
            <InlineError error={error} />
            <button className="btn btn-primary" type="submit" disabled={pending}>
              {pending ? "Finding people…" : "Find people"}
            </button>
            <span className="hint">Hermes ranks from demonstrated skills. You still choose.</span>
          </div>
          <details className="disclosure">
            <summary>Advanced</summary>
            <label className="field">
              <span className="label">Request id</span>
              <input name="request_id" className="input mono" value={requestId} onChange={(e) => setRequestId(e.target.value)} required pattern="[A-Za-z0-9][A-Za-z0-9._:\-]{0,127}" />
              <span className="hint">Letters, digits and . _ : - only. Re-using an open request id you own re-ranks it.</span>
            </label>
            <label className="field">
              <span className="label">Minimum coverage (0–1)</span>
              <input name="min_coverage_ratio" className="input num" type="number" min={0} max={1} step={0.05} value={minCoverage} placeholder="Engine default" onChange={(e) => setMinCoverage(e.target.value)} />
            </label>
            <label className="field">
              <span className="label">Shortlist size</span>
              <input name="shortlist_size" className="input num" type="number" min={1} max={10} value={shortlist} onChange={(e) => setShortlist(Number(e.target.value))} />
            </label>
          </details>
        </div>
      </aside>
    </form>
  );
}
