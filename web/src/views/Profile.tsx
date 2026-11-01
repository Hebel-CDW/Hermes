import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";
import { learningApi, profileApi, skillsApi } from "../api/endpoints";
import type { MeResult } from "../api/types";
import { hasRole, useAuth } from "../lib/auth";
import { confidenceWords, freshnessWords, LEVEL_NAMES, levelName, mixWords } from "../lib/explain";
import { int, pct, shortTime } from "../lib/format";
import { useSkillName } from "../lib/skills";
import { useApi } from "../lib/useApi";
import { Bar, Kpi, Levels, PageHead } from "../ui/Bits";
import { HowToRead, ToneChip } from "../ui/Explain";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

/** The subject is always the signed-in principal: /api/me takes no identity parameter. */
export default function Profile() {
  const { session } = useAuth();
  const canSelf = hasRole(session, "employee", "manager");
  return (
    <>
      <PageHead
        trail={["My skills"]}
        title="My skills"
        lede="What Hermes knows about your skills, how sure it is, and where you could grow next."
      />
      {session && (
        <details className="panel disclosure-panel">
          <summary className="panel-head" style={{ cursor: "pointer" }}>
            <h2>Account details</h2>
          </summary>
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
        </details>
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
  const skills = [...me.skills].sort((x, y) => y.proficiency - x.proficiency || y.confidence - x.confidence);
  const strongest = skills[0];
  const meanConf = skills.length ? skills.reduce((t, s) => t + s.confidence, 0) / skills.length : null;
  const stale = skills.filter((s) => s.freshness < 0.5);
  const conf = confidenceWords(meanConf);
  return (
    <>
      <section className="verdict verdict-neutral" aria-label="Your summary" data-testid="me-summary">
        <div className="label">In plain English</div>
        <h2>
          {skills.length === 0
            ? "Hermes has no proof of your skills yet"
            : `Hermes holds proof of ${skills.length} skill${skills.length === 1 ? "" : "s"} for you`}
        </h2>
        {skills.length > 0 && (
          <p>
            It is backed by {me.evidence.length} piece{me.evidence.length === 1 ? "" : "s"} of evidence. Your strongest skill is{" "}
            <strong>{skillName(strongest.skill_id)}</strong> at {levelName(strongest.proficiency)}.{" "}
            {stale.length === 0
              ? "All of your proof is recent."
              : `${stale.length} skill${stale.length === 1 ? " is" : "s are"} getting old (${stale.map((s) => skillName(s.skill_id)).join(", ")}); recent work on ${stale.length === 1 ? "it" : "them"} would refresh the score.`}
          </p>
        )}
      </section>

      <section className="kpis" aria-label="Your figures">
        <Kpi label="Skills with proof" value={int(skills.length)} />
        <Kpi label="Strongest" value={strongest ? `L${strongest.proficiency}` : "—"} note={strongest ? skillName(strongest.skill_id) : "Nothing yet"} />
        <Kpi label="How sure we are" value={meanConf === null ? "—" : pct(meanConf, 0)} note={conf.label} />
        <Kpi label="Needs fresh proof" value={int(stale.length)} note={stale.length ? "skills getting old" : "all recent"} />
      </section>

      <section className="panel section">
        <div className="panel-head">
          <h2>Your skills, explained</h2>
          <span className="mono muted" style={{ fontSize: 12 }}>
            {me.coded_identity}
          </span>
        </div>
        {skills.length === 0 ? (
          <div className="panel-body muted">No skills have been inferred for you yet.</div>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Skill</th>
                  <th>Level</th>
                  <th>How sure</th>
                  <th>Backed by</th>
                  <th>Recent?</th>
                  <th>To strengthen it</th>
                  <th className="right">Volume</th>
                </tr>
              </thead>
              <tbody>
                {skills.map((s) => {
                  const c = confidenceWords(s.confidence);
                  return (
                    <tr key={s.skill_id} data-testid="me-skill">
                      <td>{skillName(s.skill_id)}</td>
                      <td>
                        <Levels level={s.proficiency} /> <span className="muted num">L{s.proficiency}</span>
                        <div className="muted" style={{ fontSize: 12 }}>
                          {LEVEL_NAMES[s.proficiency]}
                        </div>
                      </td>
                      <td>
                        <ToneChip tone={c.tone} title={c.text}>
                          {c.label} · {pct(s.confidence, 0)}
                        </ToneChip>
                      </td>
                      <td className="muted">{mixWords(s.evidence_ids)}</td>
                      <td>
                        {freshnessWords(s.freshness)}
                        <div className="muted num" style={{ fontSize: 12 }}>
                          {pct(s.freshness, 0)}
                        </div>
                      </td>
                      <td className="muted" style={{ whiteSpace: "normal", minWidth: 240 }}>
                        {strengthenHint(s)}
                      </td>
                      <td className="right num">{pct(s.volume_score)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <RoleReadiness codedIdentity={me.coded_identity} />

      <div className="grid cols-2 section">
        <section className="panel">
          <div className="panel-head">
            <h2>Evidence behind your skills</h2>
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
                      {EVIDENCE_WORDS[e.evidence_type] ?? e.evidence_type}
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
        <div style={{ display: "grid", gap: 16, alignContent: "start" }}>
          {(me.contests ?? []).length > 0 && (
            <section className="panel" aria-label="Your open disputes" data-testid="my-contests">
              <div className="panel-head">
                <h2>Your open disputes</h2>
                <span className="chip chip-warn">With your manager</span>
              </div>
              <ul className="activity">
                {(me.contests ?? []).map((c) => (
                  <li key={c.contest_id}>
                    <span>
                      <strong>{c.skill_id ? skillName(c.skill_id) : "General"}</strong>
                      <span className="muted" style={{ display: "block", fontSize: 13 }}>
                        {c.reason}
                      </span>
                    </span>
                    <span className="muted num">{shortTime(c.created_at)}</span>
                  </li>
                ))}
              </ul>
              <p className="muted" style={{ margin: 0, padding: "0 16px 14px", fontSize: 13 }}>
                Your manager can confirm the skill or dismiss it. Confirming adds a manager-confirmed claim to your record.
              </p>
            </section>
          )}
          <ContestForm skills={me.skills.map((s) => s.skill_id)} />
        </div>
      </div>

      <HowToRead />
    </>
  );
}

const EVIDENCE_WORDS: Record<string, string> = { demonstrated: "Real work", certified: "Certificate", declared: "Claimed" };

function strengthenHint(s: MeResult["skills"][number]): string {
  if (s.freshness < 0.5) return "Do recent work on this skill; old proof counts for less.";
  if (s.confidence < 0.6) return "Add a certificate or ask your manager to confirm it. One kind of proof is all that is on file.";
  if (s.proficiency < 4) return "More complex tickets on this skill would lift your level.";
  return "Strong. Keep it current.";
}

/** How close the signed-in person is to each role, from the engine's own gap analysis. */
function RoleReadiness({ codedIdentity }: { codedIdentity: string }) {
  const skillName = useSkillName();
  const q = useApi(async (signal) => {
    const { roles } = await skillsApi.roles(signal);
    return Promise.all(
      roles.map(async (role) => ({ role, gaps: (await learningApi.gaps(codedIdentity, role)).gaps })),
    );
  }, [codedIdentity]);
  if (q.status !== "success" || q.data.length === 0) return null;
  const cards = q.data
    .map(({ role, gaps }) => {
      const need = Object.keys(role.required_skills).length;
      const met = need - gaps.length;
      const criticalMissing = gaps.some((g) => g.current_level === null && role.critical_skills.includes(g.skill_id));
      return { role, gaps, need, met, ratio: need ? met / need : 0, criticalMissing };
    })
    .sort((a, b) => b.ratio - a.ratio || a.gaps.length - b.gaps.length)
    .slice(0, 4);
  return (
    <section className="section" aria-label="Roles you could grow into" data-testid="role-readiness">
      <h2 style={{ fontSize: 16, margin: "0 0 4px" }}>Roles you could grow into</h2>
      <p className="muted" style={{ margin: "0 0 10px" }}>
        How close your proof is to each role. This is the same check your manager sees when they look for someone.
      </p>
      <div className="grid cols-2">
        {cards.map(({ role, gaps, need, met, ratio, criticalMissing }) => (
          <article className="panel" key={role.role_id}>
            <div className="panel-head">
              <h3 style={{ margin: 0, fontSize: 15 }}>{role.role_name}</h3>
              <ToneChip tone={ratio === 1 ? "good" : ratio >= 0.5 && !criticalMissing ? "warn" : "neutral"}>
                {ratio === 1 ? "You meet it" : ratio >= 0.5 && !criticalMissing ? "Within reach" : "A stretch"}
              </ToneChip>
            </div>
            <div className="panel-body">
              <div className="muted" style={{ marginBottom: 6 }}>
                You meet {met} of {need} requirements
              </div>
              <Bar value={ratio} tone={ratio === 1 ? undefined : "crimson"} />
              <ul style={{ margin: "10px 0 0", paddingLeft: 18 }}>
                {gaps.map((g) => (
                  <li key={g.skill_id} className="ink-2">
                    {skillName(g.skill_id)}:{" "}
                    {g.current_level === null ? "no proof yet" : `you are at level ${g.current_level}`}, the role needs level {g.required_level}
                    {role.critical_skills.includes(g.skill_id) ? " (critical)" : ""}.
                  </li>
                ))}
                {gaps.length === 0 && <li className="ink-2">Nothing missing. Ask your manager about this role.</li>}
              </ul>
              <Link className="btn btn-sm" to="/learning" style={{ marginTop: 10 }}>
                See your learning path
              </Link>
            </div>
          </article>
        ))}
      </div>
    </section>
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
