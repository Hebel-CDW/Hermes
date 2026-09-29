import { FormEvent, useState } from "react";
import { profileApi, skillsApi } from "../api/endpoints";
import type { MeResult } from "../api/types";
import { hasRole, useAuth } from "../lib/auth";
import { pct, shortTime } from "../lib/format";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { Levels, PageHead } from "../ui/Bits";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

/** The subject is always the signed-in principal: /api/me takes no identity parameter. */
export default function Profile() {
  const { session } = useAuth();
  const canSelf = hasRole(session, "employee", "manager");
  return (
    <>
      <PageHead
        trail={["System", "Profile"]}
        title="Profile"
        lede="Your skills, and the proof Hermes holds about you. If something looks wrong, tell your manager below."
      />
      {session && (
        <section className="panel">
          <div className="panel-body">
            <dl className="dl" style={{ maxWidth: 520 }}>
              <dt>Principal</dt>
              <dd data-testid="session-sub">{session.sub}</dd>
              <dt>Roles</dt>
              <dd>{session.roles.join(", ")}</dd>
              <dt>Coded identity</dt>
              <dd className="mono" data-testid="session-coded">
                {session.coded_identity ?? "None"}
              </dd>
            </dl>
          </div>
        </section>
      )}
      <div className="section">
        {canSelf && !session?.coded_identity ? (
          <EmptyState title="No personal skill profile">
            Your principal is not mapped to a coded identity in this database, so there is no evidence to show.
          </EmptyState>
        ) : canSelf ? (
          <SelfEvidence key={session?.sub} />
        ) : (
          <EmptyState title="No personal skill profile">Administrator principals are not mapped to a coded identity.</EmptyState>
        )}
      </div>
    </>
  );
}

function SelfEvidence() {
  const q = useApi((s) => profileApi.me(s), []);
  if (q.status === "loading") return <Loading label="Loading your evidence" />;
  if (q.status === "error") return <ErrorState error={q.error} onRetry={q.reload} />;
  return <SelfBody me={q.data} />;
}

function SelfBody({ me }: { me: MeResult }) {
  const skillName = useSkillName();
  return (
    <>
      <section className="panel">
        <div className="panel-head">
          <h2>Your skills</h2>
          <span className="mono muted" style={{ fontSize: 12 }}>
            {me.coded_identity}
          </span>
        </div>
        {me.skills.length === 0 ? (
          <div className="panel-body muted">No skills have been inferred for you yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Skill</th>
                  <th>Level</th>
                  <th className="right">Confidence</th>
                  <th className="right">Freshness</th>
                  <th className="right">Volume</th>
                </tr>
              </thead>
              <tbody>
                {me.skills.map((s) => (
                  <tr key={s.skill_id} data-testid="me-skill">
                    <td>{skillName(s.skill_id)}</td>
                    <td>
                      <Levels level={s.proficiency} /> <span className="muted num">L{s.proficiency}</span>
                    </td>
                    <td className="right num">{pct(s.confidence)}</td>
                    <td className="right num">{pct(s.freshness)}</td>
                    <td className="right num">{pct(s.volume_score)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <div className="grid cols-2 section">
        <section className="panel">
          <div className="panel-head">
            <h2>Evidence</h2>
            <span className="muted" style={{ fontSize: 12 }}>
              {me.evidence.length} records
            </span>
          </div>
          {me.evidence.length === 0 ? (
            <div className="panel-body muted">No evidence records.</div>
          ) : (
            <ul className="activity">
              {me.evidence.map((e) => (
                <li key={e.evidence_id}>
                  <span>
                    <span className="chip" style={{ marginRight: 8 }}>
                      {e.evidence_type}
                    </span>
                    {skillName(e.skill_id)}
                    <span className="mono muted" style={{ display: "block", fontSize: 12 }}>
                      {e.source_ref}
                    </span>
                  </span>
                  <span className="muted num">{shortTime(e.occurred_at)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <ContestForm skills={me.skills.map((s) => s.skill_id)} />
      </div>
    </>
  );
}

function ContestForm({ skills }: { skills: string[] }) {
  const skillName = useSkillName();
  const governed = useApi((s) => skillsApi.list(s), []);
  const options = governed.status === "success" ? governed.data.skills.map((s) => s.skill_id) : skills;
  const [skill, setSkill] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [done, setDone] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    setDone(null);
    try {
      const r = await profileApi.contest(reason, skill || undefined);
      setDone(r.contest_id);
      setReason("");
    } catch (err) {
      setError(err as Error);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Something look wrong?</h2>
      </div>
      <form className="panel-body" onSubmit={submit}>
        <label className="field">
          <span className="label">Skill (optional)</span>
          <select name="skill_id" className="select" value={skill} onChange={(e) => setSkill(e.target.value)}>
            <option value="">General</option>
            {options.map((s) => (
              <option key={s} value={s}>
                {skillName(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="label">Reason</span>
          <textarea name="reason" className="textarea" required maxLength={2000} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <div className="field">
          <InlineError error={error} />
          {done && (
            <div className="inline-ok" role="status">
              Sent to your manager to review. <span className="mono muted">Ref {done.slice(0, 8)}</span>
            </div>
          )}
          <button className="btn btn-primary" type="submit" disabled={pending || !reason.trim()} style={{ justifySelf: "start" }}>
            {pending ? "Sending…" : "Send to my manager"}
          </button>
        </div>
      </form>
    </section>
  );
}
