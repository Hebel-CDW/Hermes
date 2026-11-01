import { useState } from "react";
import { learningApi, skillsApi, workforceApi } from "../api/endpoints";
import type { GapResult, RoleProfile, Session } from "../api/types";
import { hasRole, useAuth } from "../lib/auth";
import { fixed } from "../lib/format";
import { useNames } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

export default function Learning() {
  const { session } = useAuth();
  const q = useApi(
    async (s) => {
      const roles = (await skillsApi.roles(s)).roles;
      const staff = hasRole(session, "manager", "admin");
      const reports = staff ? (await workforceApi.directReports(s)).identities : [];
      const subjects = [...new Set([...(session?.coded_identity ? [session.coded_identity] : []), ...reports])];
      return { roles, subjects };
    },
    [session?.sub],
  );
  return (
    <>
      <PageHead
        trail={["Learning & Gaps"]}
        title="Learning & Gaps"
        lede="What should this person learn next, against a role they are aiming for."
      />
      {q.status === "loading" && <Loading label="Loading learning" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (q.data.roles.length === 0 ? (
          <EmptyState title="No role profiles">Define a governed role profile to analyse development gaps.</EmptyState>
        ) : q.data.subjects.length === 0 ? (
          <EmptyState title="No coded identity available">Your principal has no coded identity and no direct reports in this database.</EmptyState>
        ) : (
          <GapAnalysis key={session?.sub} session={session!} roles={q.data.roles} subjects={q.data.subjects} />
        ))}
    </>
  );
}

function GapAnalysis({ session, roles, subjects }: { session: Session; roles: RoleProfile[]; subjects: string[] }) {
  const { label } = useNames();
  const skillName = useSkillName();
  const [subject, setSubject] = useState(subjects[0]);
  const [roleId, setRoleId] = useState(roles[0].role_id);
  const [result, setResult] = useState<GapResult | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const role = roles.find((r) => r.role_id === roleId)!;

  const run = async () => {
    setPending(true);
    setError(null);
    setResult(null);
    try {
      setResult(await learningApi.gaps(subject, { role_id: role.role_id, role_name: role.role_name, required_skills: role.required_skills }));
    } catch (e) {
      setError(e as Error);
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <section className="panel">
        <div className="panel-body" style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
          <label className="field" style={{ minWidth: 220, flex: 1 }}>
            <span className="label">Person</span>
            <select name="subject" className="select" value={subject} onChange={(e) => (setSubject(e.target.value), setResult(null))}>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {s === session.coded_identity && label(s) === s ? "You" : label(s)}
                  {s === session.coded_identity && label(s) !== s ? " (you)" : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field" style={{ minWidth: 220, flex: 1, marginTop: 0 }}>
            <span className="label">Target role</span>
            <select name="role" className="select" value={roleId} onChange={(e) => (setRoleId(e.target.value), setResult(null))}>
              {roles.map((r) => (
                <option key={r.role_id} value={r.role_id}>
                  {r.role_name}
                </option>
              ))}
            </select>
          </label>
          <button className="btn btn-primary" onClick={run} disabled={pending}>
            {pending ? "Looking…" : "See what they should learn"}
          </button>
        </div>
      </section>

      <div className="section">
        <InlineError error={error} />
        {!result && !error && !pending && (
          <EmptyState title="Choose a person and role">Pick someone, then see what they should learn.</EmptyState>
        )}
        {pending && <Loading label="Looking at skill gaps" rows={2} />}
        {result && (
          <>
            {result.gaps.length === 0 ? (
              <EmptyState title="No gaps">
                <span className="mono">{label(result.coded_identity)}</span> meets every required level for {role.role_name}.
              </EmptyState>
            ) : (
              <div className="grid" style={{ gap: 16 }}>
                {result.gaps.map((g) => (
                  <section className="panel" key={g.skill_id} data-testid="gap">
                    <div className="panel-head">
                      <h2>{skillName(g.skill_id)}</h2>
                      <span className="chip" title="How much open demand depends on this skill">
                        Priority {fixed(g.demand_impact, 1)}
                      </span>
                    </div>
                    <div className="panel-body">
                      <div className="stepper" aria-label={`Current level ${g.current_level ?? "none"}, target level ${g.required_level}`}>
                        {[1, 2, 3, 4, 5].map((l) => (
                          <div key={l} className={`step ${g.current_level === l ? "current" : ""} ${g.required_level === l ? "target" : ""}`}>
                            <b>{l}</b>
                            <span>{g.current_level === l ? "Current" : g.required_level === l ? "Target" : ""}</span>
                          </div>
                        ))}
                      </div>
                      {g.current_level === null && (
                        <p className="hint">
                          No direct proof of this skill on file. Related skills can still earn partial credit on the Who fits page.
                        </p>
                      )}
                      <p className="muted" style={{ marginBottom: 0, fontSize: 13 }}>
                        {g.current_level === null
                          ? `The role needs level ${g.required_level}.`
                          : `The role needs level ${g.required_level}. They are at level ${g.current_level}.`}
                      </p>
                      <details style={{ marginTop: 8 }}>
                        <summary className="muted" style={{ cursor: "pointer", fontSize: 12 }}>
                          How this was worked out
                        </summary>
                        <p className="muted mono" style={{ margin: "6px 0 0", fontSize: 12 }}>
                          {g.reasoning}
                        </p>
                      </details>
                    </div>
                  </section>
                ))}
              </div>
            )}
            <div className="section">
              <EmptyState title="No learning catalogue connected">
                Hermes does not generate or invent courses. Recommended courses will appear here once a learning catalogue is connected.
              </EmptyState>
            </div>
            <div className="footer-meta">
              <span>
                Scoring config <span className="mono">{result.scoring_config_version}</span>
              </span>
            </div>
          </>
        )}
      </div>
    </>
  );
}
