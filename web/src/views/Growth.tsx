import { AnimatePresence, motion } from "framer-motion";
import { FormEvent, useState } from "react";
import { learningApi, skillsApi, workflowApi } from "../api/endpoints";
import type { CertEntry, ChangeRequest, GapItem, Goal, RoleProfile, SkillSummaryRow, SubmitBody, TimelineEvent } from "../api/types";
import { useAuth } from "../lib/auth";
import { shortTime } from "../lib/format";
import { useSkillName } from "../lib/skills";
import { useApi, useStale } from "../lib/useApi";
import { Levels, PageHead } from "../ui/Bits";
import { Burst, GoalRing, Rise, Stagger, useCalm, useToasts } from "../ui/Fx";
import { ErrorState, InlineError, Loading } from "../ui/States";

const LEVELS: [number, string][] = [
  [1, "1 Awareness"],
  [2, "2 Working"],
  [3, "3 Proficient"],
  [4, "4 Advanced"],
  [5, "5 Expert"],
];

const STATUS_TEXT: Record<string, string> = {
  pending: "Waiting for your manager",
  approved: "Approved",
  declined: "Declined",
  withdrawn: "Withdrawn",
};
const STATUS_TONE: Record<string, string> = { pending: "chip-warn", approved: "chip-ok", declined: "chip-crimson", withdrawn: "" };

type Data = {
  mine: { requests: ChangeRequest[]; goal: Goal | null };
  events: TimelineEvent[];
  roles: RoleProfile[];
  skills: SkillSummaryRow[];
  certs: CertEntry[];
};

export default function Growth() {
  const [tick, setTick] = useState(0);
  const refresh = () => setTick((n) => n + 1);
  const q = useApi<Data>(
    async (s) => {
      const [mine, timeline, roles, skills, certs] = await Promise.all([
        workflowApi.mine(s),
        workflowApi.timeline(s),
        skillsApi.roles(s),
        skillsApi.list(s),
        workflowApi.certCatalog(s),
      ]);
      return { mine, events: timeline.events, roles: roles.roles, skills: skills.skills, certs: certs.certificates };
    },
    [tick],
  );
  const data = useStale(q);
  return (
    <>
      <PageHead trail={["Growth"]} title="My growth" lede="Pick where you want to go, tell your manager what you have learned, and watch your record move." />
      {q.status === "loading" && !data && <Loading label="Loading your growth plan" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data && <GrowthBody data={data} refresh={refresh} />}
    </>
  );
}

function GrowthBody({ data, refresh }: { data: Data; refresh: () => void }) {
  const [fire, setFire] = useState(0);
  const [prefill, setPrefill] = useState<{ skill_id: string; level: number } | null>(null);
  const { push, host } = useToasts();
  const celebrate = (text: string) => {
    push(text, "ok");
    setFire((n) => n + 1);
    refresh();
  };
  const changed = (text: string) => {
    push(text, "info");
    refresh();
  };
  return (
    <>
      <Burst fire={fire} />
      {host}
      <GoalPanel goal={data.mine.goal} roles={data.roles} refresh={refresh} onPropose={(skill_id, level) => setPrefill({ skill_id, level })} />
      <div className="grid cols-2" style={{ marginTop: 20 }}>
        <ProposePanel skills={data.skills} certs={data.certs} prefill={prefill} onDone={celebrate} />
        <RequestsPanel requests={data.mine.requests} onChanged={changed} />
      </div>
      <Timeline events={data.events} />
    </>
  );
}

/* ----------------------------------------------------------------- goal */
function GoalPanel({
  goal,
  roles,
  refresh,
  onPropose,
}: {
  goal: Goal | null;
  roles: RoleProfile[];
  refresh: () => void;
  onPropose: (skill_id: string, level: number) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const run = async (job: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await job();
      refresh();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(false);
    }
  };

  if (!goal) {
    return (
      <section className="panel">
        <div className="panel-head">
          <h2>Where do you want to grow?</h2>
        </div>
        <div className="panel-body">
          <p className="ink-2" style={{ marginTop: 0 }}>
            Choose a role. Hermes shows exactly what stands between you and it, skill by skill.
          </p>
          <InlineError error={error} />
          <Stagger className="role-cards" gap={0.05}>
            {roles.map((r) => (
              <Rise key={r.role_id}>
                <button className="role-card" disabled={busy} onClick={() => run(() => workflowApi.setGoal(r.role_id))} aria-label={`Aim for ${r.role_name}`}>
                  <strong>{r.role_name}</strong>
                  <span className="muted">{Object.keys(r.required_skills).length} skills</span>
                </button>
              </Rise>
            ))}
          </Stagger>
        </div>
      </section>
    );
  }
  return <GoalProgress goal={goal} busy={busy} error={error} onClear={() => run(() => workflowApi.clearGoal())} onPropose={onPropose} />;
}

function GoalProgress({
  goal,
  busy,
  error,
  onClear,
  onPropose,
}: {
  goal: Goal;
  busy: boolean;
  error: Error | null;
  onClear: () => void;
  onPropose: (skill_id: string, level: number) => void;
}) {
  const { session } = useAuth();
  const skillName = useSkillName();
  const calm = useCalm();
  const q = useApi(
    () => learningApi.gaps(session!.coded_identity!, { role_id: goal.role_id, role_name: goal.role_name, required_skills: goal.required_skills }),
    [goal.role_id, session?.coded_identity],
  );
  const gaps = q.status === "success" ? q.data.gaps : [];
  const met = gaps.filter((g) => (g.current_level ?? 0) >= g.required_level).length;
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Your path to {goal.role_name}</h2>
        <button className="btn btn-ghost btn-sm" disabled={busy} onClick={onClear}>
          Change goal
        </button>
      </div>
      <div className="panel-body">
        <InlineError error={error} />
        {q.status === "loading" && <Loading label="Working out your gaps" rows={2} />}
        {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
        {q.status === "success" && (
          <div className="goal-layout">
            <div className="goal-ring">
              <GoalRing value={gaps.length ? met / gaps.length : 0} label="Skills at the level this role needs" sub={`${met} of ${gaps.length} skills`} />
            </div>
            <ul className="goal-skills">
              {gaps.map((g, i) => (
                <GoalRow key={g.skill_id} g={g} index={i} name={skillName(g.skill_id)} calm={calm} onPropose={onPropose} />
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

function GoalRow({ g, index, name, calm, onPropose }: { g: GapItem; index: number; name: string; calm: boolean; onPropose: (id: string, level: number) => void }) {
  const have = g.current_level ?? 0;
  const ready = have >= g.required_level;
  const behind = g.required_level - have;
  return (
    <motion.li
      initial={calm ? false : { opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: calm ? 0 : 0.08 * index, duration: 0.3 }}
      className={ready ? "ready" : ""}
    >
      <div className="goal-skill-head">
        <strong>{name}</strong>
        <span className={`chip ${ready ? "chip-ok" : have ? "chip-warn" : ""}`}>
          {ready ? "At the level" : have ? `${behind} level${behind === 1 ? "" : "s"} to go` : "No proof yet"}
        </span>
      </div>
      <div className="goal-track" role="img" aria-label={`${name}: you are at ${have || "no"} level, the role needs ${g.required_level}`}>
        <motion.span
          className="goal-fill"
          initial={calm ? false : { width: 0 }}
          animate={{ width: `${(have / 5) * 100}%` }}
          transition={{ duration: 0.8, delay: calm ? 0 : 0.1 * index }}
        />
        <i className="goal-target" style={{ left: `${(g.required_level / 5) * 100}%` }} />
      </div>
      <div className="goal-skill-foot">
        <Levels level={have || null} />
        <span className="muted">needs level {g.required_level}</span>
        {!ready && (
          <button className="btn btn-ghost btn-sm" onClick={() => onPropose(g.skill_id, Math.min(5, Math.max(have, g.required_level)))}>
            I have this now
          </button>
        )}
      </div>
    </motion.li>
  );
}

/* -------------------------------------------------------------- propose */
type Tab = "skill_claim" | "certificate" | "skill_check";
const TAB_TEXT: [Tab, string][] = [
  ["skill_claim", "A skill"],
  ["certificate", "A certificate"],
  ["skill_check", "Ask for a check"],
];

function ProposePanel({
  skills,
  certs,
  prefill,
  onDone,
}: {
  skills: SkillSummaryRow[];
  certs: CertEntry[];
  prefill: { skill_id: string; level: number } | null;
  onDone: (text: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("skill_claim");
  const [skillId, setSkillId] = useState(skills[0]?.skill_id ?? "");
  const [level, setLevel] = useState(3);
  const [cert, setCert] = useState(certs[0]?.code ?? "");
  const [date, setDate] = useState("");
  const [note, setNote] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [lastPrefill, setLastPrefill] = useState(prefill);
  if (prefill !== lastPrefill) {
    setLastPrefill(prefill);
    if (prefill) {
      setTab("skill_claim");
      setSkillId(prefill.skill_id);
      setLevel(prefill.level);
    }
  }
  const today = new Date().toISOString().slice(0, 10);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setPending(true);
    setError(null);
    const trimmed = note.trim();
    const extra = trimmed ? { note: trimmed } : {};
    const body: SubmitBody =
      tab === "skill_claim"
        ? { kind: "skill_claim", skill_id: skillId, proficiency: level, ...extra }
        : tab === "skill_check"
          ? { kind: "skill_check", skill_id: skillId, ...extra }
          : { kind: "certificate", cert_code: cert, earned_at: date, ...extra };
    try {
      await workflowApi.submit(body);
      setNote("");
      onDone("Sent to your manager. It counts once they approve it.");
    } catch (err) {
      setError(err as Error);
    } finally {
      setPending(false);
    }
  };

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>Tell your manager</h2>
      </div>
      <form className="panel-body" onSubmit={submit}>
        <div className="seg" role="tablist" aria-label="What are you sending?">
          {TAB_TEXT.map(([k, label]) => (
            <button type="button" key={k} role="tab" aria-selected={tab === k} className={tab === k ? "on" : ""} onClick={() => setTab(k)}>
              {label}
            </button>
          ))}
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={tab} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.16 }}>
            {tab !== "certificate" ? (
              <>
                <label className="field">
                  <span className="label">Skill</span>
                  <select className="select" aria-label="Skill" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
                    {skills.map((s) => (
                      <option key={s.skill_id} value={s.skill_id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                {tab === "skill_claim" && (
                  <label className="field">
                    <span className="label">Your level</span>
                    <select className="select" aria-label="Your level" value={level} onChange={(e) => setLevel(Number(e.target.value))}>
                      {LEVELS.map(([n, text]) => (
                        <option key={n} value={n}>
                          {text}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {tab === "skill_check" && <p className="hint">Your manager picks the level after seeing your work. Nothing is claimed.</p>}
              </>
            ) : (
              <>
                <label className="field">
                  <span className="label">Certificate</span>
                  <select className="select" aria-label="Certificate" value={cert} onChange={(e) => setCert(e.target.value)}>
                    {certs.map((c) => (
                      <option key={c.code} value={c.code}>
                        {c.code} · {c.skill_name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span className="label">Date you earned it</span>
                  <input className="input" type="date" aria-label="Date you earned it" max={today} value={date} onChange={(e) => setDate(e.target.value)} required />
                </label>
              </>
            )}
          </motion.div>
        </AnimatePresence>
        <label className="field">
          <span className="label">Anything your manager should know (optional)</span>
          <input className="input" aria-label="Note" maxLength={300} value={note} placeholder="e.g. led the migration in March" onChange={(e) => setNote(e.target.value)} />
        </label>
        <InlineError error={error} />
        <button className="btn btn-primary" type="submit" disabled={pending || (tab === "certificate" && !date)}>
          {pending ? "Sending…" : "Send to my manager"}
        </button>
        <p className="hint">Tickets and certificates still count more than a claim, so this never replaces real work.</p>
      </form>
    </section>
  );
}

/* ------------------------------------------------------------- requests */
function RequestsPanel({ requests, onChanged }: { requests: ChangeRequest[]; onChanged: (t: string) => void }) {
  const skillName = useSkillName();
  const [error, setError] = useState<Error | null>(null);
  const withdraw = async (id: string) => {
    setError(null);
    try {
      await workflowApi.withdraw(id);
      onChanged("Request withdrawn");
    } catch (e) {
      setError(e as Error);
    }
  };
  return (
    <section className="panel">
      <div className="panel-head">
        <h2>What I have sent</h2>
      </div>
      <div className="panel-body">
        <InlineError error={error} />
        {requests.length === 0 ? (
          <p className="ink-2" style={{ margin: 0 }}>
            Nothing yet. When you send your manager something, you can follow it here.
          </p>
        ) : (
          <ul className="req-list">
            <AnimatePresence initial={false}>
              {requests.map((r) => (
                <motion.li key={r.request_id} layout initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} data-testid="my-request">
                  <div className="req-main">
                    <strong>{r.kind === "certificate" ? `${r.payload.cert_code} certificate` : skillName(r.payload.skill_id ?? "")}</strong>
                    <span className="muted">
                      {r.kind === "skill_claim" ? `Level ${r.payload.proficiency}` : r.kind === "skill_check" ? "Check requested" : r.payload.earned_at?.slice(0, 10)} · {shortTime(r.created_at)}
                    </span>
                    {r.decision_note && <span className="req-note">Manager: “{r.decision_note}”</span>}
                  </div>
                  <div className="req-side">
                    <span className={`chip ${STATUS_TONE[r.status]}`}>{STATUS_TEXT[r.status]}</span>
                    {r.status === "pending" && (
                      <button className="btn btn-ghost btn-sm" onClick={() => withdraw(r.request_id)}>
                        Withdraw
                      </button>
                    )}
                  </div>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- timeline */
function Timeline({ events }: { events: TimelineEvent[] }) {
  const calm = useCalm();
  return (
    <section className="panel" style={{ marginTop: 20 }}>
      <div className="panel-head">
        <h2>Your timeline</h2>
        <span className="muted">Everything that changed on your record</span>
      </div>
      <div className="panel-body">
        {events.length === 0 ? (
          <p className="ink-2" style={{ margin: 0 }}>
            Nothing has changed on your record yet.
          </p>
        ) : (
          <ol className="timeline">
            {events.map((e, i) => (
              <motion.li
                key={e.seq}
                initial={calm ? false : { opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: calm ? 0 : Math.min(i, 8) * 0.05 }}
              >
                <span className="timeline-dot" aria-hidden />
                <div>
                  <strong>{e.title}</strong>
                  {e.detail && <span className="ink-2"> · {e.detail}</span>}
                  <div className="muted num">{shortTime(e.at)}</div>
                </div>
              </motion.li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}
