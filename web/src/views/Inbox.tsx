import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { managerToolsApi, teamApi } from "../api/endpoints";
import type { ChangeRequest, InboxContest } from "../api/types";
import { shortTime } from "../lib/format";
import { PersonName } from "../lib/names";
import { useSkillName } from "../lib/skills";
import { useApi, useStale } from "../lib/useApi";
import { Kpi, Levels, PageHead } from "../ui/Bits";
import { Burst, CountUp, Rise, Stagger, useCalm, useToasts } from "../ui/Fx";
import { notifyInboxChanged } from "../ui/InboxNudge";
import { ErrorState, InlineError, Loading } from "../ui/States";

const LEVELS: [number, string][] = [
  [1, "1 Awareness"],
  [2, "2 Working"],
  [3, "3 Proficient"],
  [4, "4 Advanced"],
  [5, "5 Expert"],
];

type Filter = "all" | "skill_claim" | "certificate" | "skill_check" | "contest";
const FILTERS: [Filter, string][] = [
  ["all", "Everything"],
  ["skill_claim", "Skill claims"],
  ["certificate", "Certificates"],
  ["skill_check", "Skill checks"],
  ["contest", "Disputes"],
];

const KIND_LABEL: Record<string, string> = {
  skill_claim: "Skill claim",
  certificate: "Certificate",
  skill_check: "Skill check",
};

type Extra = { proficiency?: number; earned_at?: string; note?: string };

export default function Inbox() {
  const q = useApi((s) => managerToolsApi.inbox(s), []);
  const data = useStale(q);
  return (
    <>
      <PageHead
        trail={["Approvals"]}
        title="Approvals"
        lede="Your team proposes. You decide. Nothing counts toward a ranking until you approve it."
      />
      {q.status === "loading" && !data && <Loading label="Loading approvals" />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data && <InboxBody requests={data.requests} contests={data.contests} reload={q.reload} />}
    </>
  );
}

function InboxBody({ requests, contests, reload }: { requests: ChangeRequest[]; contests: InboxContest[]; reload: () => void }) {
  const [filter, setFilter] = useState<Filter>("all");
  const [gone, setGone] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [fire, setFire] = useState(0);
  const { push, host } = useToasts();
  const skillName = useSkillName();

  const liveRequests = requests.filter((r) => !gone.has(r.request_id));
  const liveContests = contests.filter((c) => !gone.has(c.contest_id));
  const count = (k: Filter) =>
    k === "all" ? liveRequests.length + liveContests.length : k === "contest" ? liveContests.length : liveRequests.filter((r) => r.kind === k).length;

  const shownRequests = filter === "all" ? liveRequests : filter === "contest" ? [] : liveRequests.filter((r) => r.kind === filter);
  const shownContests = filter === "all" || filter === "contest" ? liveContests : [];
  const total = shownRequests.length + shownContests.length;

  const done = (id: string, message: string, celebrate: boolean) => {
    setGone((g) => new Set(g).add(id));
    push(message, "ok");
    if (celebrate) setFire((n) => n + 1);
    notifyInboxChanged();
    setTimeout(reload, 600);
  };

  const run = async (id: string, job: () => Promise<void>) => {
    setBusy(id);
    setError(null);
    try {
      await job();
    } catch (e) {
      setError(e as Error);
    } finally {
      setBusy(null);
    }
  };

  const decide = (r: ChangeRequest, decision: "approve" | "decline", extra: Extra) =>
    run(r.request_id, async () => {
      await managerToolsApi.decide(r.request_id, { decision, ...extra });
      const what = skillName(r.payload.skill_id ?? "") || r.payload.cert_code || "request";
      done(r.request_id, decision === "approve" ? `Approved: ${what}` : "Declined. Nothing was recorded.", decision === "approve");
    });

  const resolveContest = (c: InboxContest, status: "confirmed" | "dismissed") =>
    run(c.contest_id, async () => {
      await teamApi.resolveContest(c.contest_id, status);
      done(c.contest_id, status === "confirmed" ? "Dispute confirmed. The skill is now on record." : "Dispute dismissed.", status === "confirmed");
    });

  const claims = shownRequests.filter((r) => r.kind === "skill_claim" && r.payload.proficiency);
  const approveAll = () =>
    run("bulk", async () => {
      let n = 0;
      for (const r of claims) {
        await managerToolsApi.decide(r.request_id, { decision: "approve", proficiency: r.payload.proficiency });
        setGone((g) => new Set(g).add(r.request_id));
        n += 1;
      }
      push(`Approved ${n} skill claims at the levels proposed`, "ok");
      setFire((x) => x + 1);
      notifyInboxChanged();
      setTimeout(reload, 600);
    });

  return (
    <>
      <Burst fire={fire} />
      {host}
      <Stagger className="kpis" gap={0.07}>
        <Rise>
          <Kpi label="Waiting for you" value={<CountUp value={count("all")} />} note={count("all") === 0 ? "All caught up" : "Oldest first"} />
        </Rise>
        <Rise>
          <Kpi label="Skill claims" value={<CountUp value={count("skill_claim")} />} />
        </Rise>
        <Rise>
          <Kpi label="Certificates" value={<CountUp value={count("certificate")} />} />
        </Rise>
        <Rise>
          <Kpi label="Disputes" value={<CountUp value={count("contest")} />} />
        </Rise>
      </Stagger>

      <div className="chip-row" role="tablist" aria-label="Filter approvals">
        {FILTERS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={filter === k} className={`pill ${filter === k ? "on" : ""}`} onClick={() => setFilter(k)}>
            {label} <span className="pill-n">{count(k)}</span>
          </button>
        ))}
        {claims.length > 1 && (
          <button className="btn btn-sm" style={{ marginLeft: "auto" }} disabled={busy !== null} onClick={approveAll}>
            Approve all {claims.length} claims at the levels proposed
          </button>
        )}
      </div>
      <InlineError error={error} />

      {total === 0 ? (
        <CaughtUp filtered={filter !== "all"} />
      ) : (
        <div className="inbox-list">
          <AnimatePresence initial={false} mode="popLayout">
            {shownRequests.map((r) => (
              <RequestCard key={r.request_id} r={r} busy={busy === r.request_id || busy === "bulk"} onDecide={decide} />
            ))}
            {shownContests.map((c) => (
              <ContestCard key={c.contest_id} c={c} busy={busy === c.contest_id} onResolve={resolveContest} />
            ))}
          </AnimatePresence>
        </div>
      )}
    </>
  );
}

function CaughtUp({ filtered }: { filtered: boolean }) {
  const calm = useCalm();
  return (
    <motion.div className="caught-up" initial={calm ? false : { opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
      <svg width="56" height="56" viewBox="0 0 56 56" aria-hidden>
        <circle cx="28" cy="28" r="25" fill="none" stroke="var(--ok)" strokeWidth="2.5" />
        <motion.path
          d="M16 29l8 8 16-18"
          fill="none"
          stroke="var(--ok)"
          strokeWidth="3.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          initial={calm ? false : { pathLength: 0 }}
          animate={{ pathLength: 1 }}
          transition={{ duration: 0.6, delay: 0.2 }}
        />
      </svg>
      <h3>{filtered ? "Nothing in this group" : "You are all caught up"}</h3>
      <p>{filtered ? "Pick another group above." : "When someone on your team proposes a skill or certificate, it lands here."}</p>
    </motion.div>
  );
}

const cardMotion = (calm: boolean) => ({
  layout: true as const,
  initial: calm ? false : { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  exit: calm ? undefined : { opacity: 0, x: 60, scale: 0.97, transition: { duration: 0.28 } },
  transition: { duration: 0.3 },
});

function RequestCard({ r, busy, onDecide }: { r: ChangeRequest; busy: boolean; onDecide: (r: ChangeRequest, d: "approve" | "decline", extra: Extra) => void }) {
  const calm = useCalm();
  const skillName = useSkillName();
  const [level, setLevel] = useState(r.payload.proficiency ?? 3);
  const [date, setDate] = useState((r.payload.earned_at ?? "").slice(0, 10));
  const [note, setNote] = useState("");
  const subject = r.kind === "certificate" ? `${r.payload.cert_code} certificate` : skillName(r.payload.skill_id ?? "");
  const extra = useMemo<Extra>(
    () => ({
      ...(r.kind !== "certificate" ? { proficiency: level } : date ? { earned_at: date } : {}),
      ...(note.trim() ? { note: note.trim() } : {}),
    }),
    [r.kind, level, date, note],
  );
  return (
    <motion.article className="inbox-card" data-testid="inbox-row" {...cardMotion(calm)}>
      <header>
        <div className="inbox-who">
          <PersonName coded={r.coded_identity} />
          <span className="chip chip-teal">{KIND_LABEL[r.kind]}</span>
        </div>
        <span className="muted num">{shortTime(r.created_at)}</span>
      </header>
      <h3>{subject}</h3>
      <p className="ink-2">
        {r.kind === "skill_claim" && (
          <>
            Says they work at <Levels level={r.payload.proficiency} /> <strong>level {r.payload.proficiency}</strong>.
          </>
        )}
        {r.kind === "skill_check" && "Asks you to confirm what level they are at. Nothing is claimed yet."}
        {r.kind === "certificate" && (
          <>
            Earned on <strong>{r.payload.earned_at?.slice(0, 10)}</strong>. Approving records it with that date.
          </>
        )}
      </p>
      {r.payload.note && <blockquote className="inbox-note">“{r.payload.note}”</blockquote>}
      <div className="inbox-actions">
        {r.kind !== "certificate" ? (
          <label className="field compact">
            <span className="label">Level you confirm</span>
            <select className="select" name={`level_${r.request_id}`} aria-label="Level you confirm" value={level} onChange={(e) => setLevel(Number(e.target.value))}>
              {LEVELS.map(([n, label]) => (
                <option key={n} value={n}>
                  {label}
                </option>
              ))}
            </select>
          </label>
        ) : (
          <label className="field compact">
            <span className="label">Date earned</span>
            <input className="input" type="date" aria-label="Date earned" value={date} onChange={(e) => setDate(e.target.value)} />
          </label>
        )}
        <label className="field compact grow">
          <span className="label">Note to them (optional)</span>
          <input className="input" aria-label="Note to them" value={note} maxLength={300} onChange={(e) => setNote(e.target.value)} />
        </label>
        <div className="inbox-buttons">
          <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => onDecide(r, "approve", extra)}>
            {r.kind === "skill_check" ? "Verify" : "Approve"}
          </button>
          <button className="btn btn-sm" disabled={busy} onClick={() => onDecide(r, "decline", note.trim() ? { note: note.trim() } : {})}>
            Decline
          </button>
        </div>
      </div>
    </motion.article>
  );
}

function ContestCard({ c, busy, onResolve }: { c: InboxContest; busy: boolean; onResolve: (c: InboxContest, s: "confirmed" | "dismissed") => void }) {
  const calm = useCalm();
  return (
    <motion.article className="inbox-card contest" data-testid="inbox-contest" {...cardMotion(calm)}>
      <header>
        <div className="inbox-who">
          <PersonName coded={c.coded_identity} />
          <span className="chip chip-warn">Dispute</span>
        </div>
        <span className="muted num">{shortTime(c.created_at)}</span>
      </header>
      <h3>{c.skill_name || "General record"}</h3>
      <blockquote className="inbox-note">“{c.reason}”</blockquote>
      <div className="inbox-buttons">
        <button className="btn btn-primary btn-sm" disabled={busy || !c.skill_id} onClick={() => onResolve(c, "confirmed")}>
          Confirm
        </button>
        <button className="btn btn-sm" disabled={busy} onClick={() => onResolve(c, "dismissed")}>
          Dismiss
        </button>
      </div>
    </motion.article>
  );
}
