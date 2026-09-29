import { FormEvent, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { skillsApi, teamApi, workforceApi } from "../api/endpoints";
import type { OpenContest, Session, SkillSummaryRow } from "../api/types";
import { hasRole, useAuth } from "../lib/auth";
import { useNames } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

const LEVELS: [number, string][] = [
  [1, "1 Awareness"],
  [2, "2 Working"],
  [3, "3 Proficient"],
  [4, "4 Advanced"],
  [5, "5 Expert"],
];

const SOURCE_LABEL: Record<string, string> = {
  demonstrated: "ticket",
  certified: "cert",
  declared: "declared",
};

export default function SkillUpdate() {
  const { session } = useAuth();
  const q = useApi(
    async (s) => {
      const skills = (await skillsApi.list(s)).skills;
      const reports = hasRole(session, "manager", "admin") ? (await workforceApi.directReports(s)).identities : [];
      const subjects = [...new Set([...(session?.coded_identity ? [session.coded_identity] : []), ...reports])];
      return { skills, subjects };
    },
    [session?.sub],
  );
  return (
    <>
      <PageHead
        trail={["Update skills"]}
        title="Update skills"
        lede="Confirm a skill you have seen. Tickets and certificates still count more."
      />
      <p className="ink-2" style={{ marginTop: -8, maxWidth: 640 }}>
        Evidence from tickets and certs updates when work happens. Review this list when someone claims a skill you have
        seen, or monthly for exceptions. You do not re-rate the whole team.
      </p>
      {q.status === "loading" && <Loading label="Loading people" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" &&
        (q.data.subjects.length === 0 ? (
          <EmptyState title="No one to update">
            Your principal has no coded identity and no direct reports in this database.
          </EmptyState>
        ) : (
          <SkillUpdateBody session={session!} skills={q.data.skills} subjects={q.data.subjects} />
        ))}
    </>
  );
}

function SkillUpdateBody({
  session,
  skills,
  subjects,
}: {
  session: Session;
  skills: SkillSummaryRow[];
  subjects: string[];
}) {
  const { label } = useNames();
  const [params, setParams] = useSearchParams();
  const requested = params.get("person");
  const subject = requested && subjects.includes(requested) ? requested : subjects[0];
  const setSubject = (coded: string) => {
    const next = new URLSearchParams(params);
    next.set("person", coded);
    setParams(next, { replace: true });
  };

  return (
    <>
      <section className="panel">
        <div className="panel-body">
          <label className="field" style={{ minWidth: 220, maxWidth: 360 }}>
            <span className="label">Person</span>
            <select name="subject" className="select" value={subject} onChange={(e) => setSubject(e.target.value)}>
              {subjects.map((s) => (
                <option key={s} value={s}>
                  {label(s)}
                  {s === session.coded_identity ? " (you)" : ""}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>
      <PersonReview key={subject} coded={subject} skills={skills} />
    </>
  );
}

function PersonReview({ coded, skills }: { coded: string; skills: SkillSummaryRow[] }) {
  const { label } = useNames();
  const skillName = useSkillName();
  const q = useApi((s) => teamApi.skillReview(coded, s), [coded]);
  const [skillId, setSkillId] = useState(skills[0]?.skill_id ?? "");
  const [level, setLevel] = useState(3);
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [saved, setSaved] = useState(false);

  const known = useMemo(() => new Set((q.status === "success" ? q.data.matrix : []).map((r) => r.skill_id)), [q]);

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    setSaved(false);
    const payload: { coded_identity: string; skill_id: string; proficiency: number; note?: string } = {
      coded_identity: coded,
      skill_id: skillId,
      proficiency: level,
    };
    const trimmed = note.trim();
    if (trimmed) payload.note = trimmed;
    try {
      await teamApi.declare(payload);
      setSaved(true);
      setNote("");
      q.reload();
    } catch (err) {
      setError(err as Error);
    } finally {
      setPending(false);
    }
  };

  const resolve = async (contestId: string, status: "confirmed" | "dismissed") => {
    setError(null);
    try {
      await teamApi.resolveContest(contestId, status);
      q.reload();
    } catch (err) {
      setError(err as Error);
    }
  };

  return (
    <div className="section" style={{ display: "grid", gap: 16 }}>
      {q.status === "loading" && <Loading label="Loading evidence" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {q.status === "success" && (
        <>
          <section className="panel">
            <div className="panel-head">
              <h2>What Hermes already knows</h2>
            </div>
            <div className="panel-body">
              {q.data.matrix.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>
                  No inferred skills yet for {label(coded)}.
                </p>
              ) : (
                <div className="table-wrap">
                  <table className="data" aria-label="Known skills">
                    <thead>
                      <tr>
                        <th>Skill</th>
                        <th>Level</th>
                        <th>Sources</th>
                      </tr>
                    </thead>
                    <tbody>
                      {q.data.matrix.map((row) => (
                        <tr key={row.skill_id}>
                          <td>{skillName(row.skill_id)}</td>
                          <td className="num">{row.proficiency}</td>
                          <td>{row.sources.map((s) => SOURCE_LABEL[s] ?? s).join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </section>

          <section className="panel">
            <div className="panel-head">
              <h2>Your update</h2>
            </div>
            <form className="panel-body" onSubmit={save}>
              <p className="ink-2">
                Tickets and certificates still count more. Use this when the work has not shown up in tickets yet.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-end" }}>
                <label className="field" style={{ minWidth: 220, flex: 1 }}>
                  <span className="label">Skill</span>
                  <select name="skill" className="select" value={skillId} onChange={(e) => setSkillId(e.target.value)} required>
                    {skills.map((s) => (
                      <option key={s.skill_id} value={s.skill_id}>
                        {s.name}
                        {known.has(s.skill_id) ? " (already on file)" : ""}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field" style={{ minWidth: 160 }}>
                  <span className="label">Level</span>
                  <select
                    name="level"
                    className="select"
                    value={level}
                    onChange={(e) => setLevel(Number(e.target.value))}
                  >
                    {LEVELS.map(([n, name]) => (
                      <option key={n} value={n}>
                        {name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label className="field">
                <span className="label">Note (optional)</span>
                <textarea name="note" className="select" rows={2} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
              </label>
              <button className="btn btn-primary" type="submit" disabled={pending || !skillId}>
                {pending ? "Saving…" : "Record this skill"}
              </button>
              <InlineError error={error} />
              {saved && (
                <p className="ink-2" role="status">
                  Saved as your confirmation. Rankings will use it at declared weight.
                </p>
              )}
            </form>
          </section>

          <Contests contests={q.data.contests} onResolve={resolve} />

          <details className="disclosure">
            <summary>Advanced</summary>
            <p className="mono muted" style={{ margin: 0 }}>
              {coded}
            </p>
          </details>
        </>
      )}
    </div>
  );
}

function Contests({
  contests,
  onResolve,
}: {
  contests: OpenContest[];
  onResolve: (id: string, status: "confirmed" | "dismissed") => void;
}) {
  const skillName = useSkillName();
  if (contests.length === 0) return null;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Pending contests</h2>
      </div>
      <div className="panel-body" style={{ display: "grid", gap: 12 }}>
        {contests.map((c) => (
          <div key={c.contest_id} data-testid="contest-row">
            <div>
              <strong>{c.skill_id ? skillName(c.skill_id) : "Unspecified skill"}</strong>
              <p className="ink-2" style={{ margin: "4px 0 8px" }}>
                {c.reason}
              </p>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-sm" type="button" disabled={!c.skill_id} onClick={() => onResolve(c.contest_id, "confirmed")}>
                Confirm
              </button>
              <button className="btn btn-sm" type="button" onClick={() => onResolve(c.contest_id, "dismissed")}>
                Dismiss
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
