import { FormEvent, useEffect, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { api, DecisionStatus, FitnessResult, Skill } from "../api/client";
import { NarrateBanner } from "../components/NarrateBanner";
import { resolvedMap, ShortlistReveal } from "../components/ShortlistReveal";
import { pageVariants } from "../motion/presets";

export function Staff() {
  const reduced = useReducedMotion();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillId, setSkillId] = useState("container_orchestration");
  const [level, setLevel] = useState(3);
  const [whatIfLevel, setWhatIfLevel] = useState(3);
  const [result, setResult] = useState<FitnessResult | null>(null);
  const [display, setDisplay] = useState<FitnessResult | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [auditStrip, setAuditStrip] = useState<string | null>(null);
  const [ceremony, setCeremony] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [decisionStatus, setDecisionStatus] = useState<DecisionStatus>("accepted");
  const [chosen, setChosen] = useState("");
  const [rejectionReason, setRejectionReason] = useState("");
  const [overrideNote, setOverrideNote] = useState("");
  const [decisionMsg, setDecisionMsg] = useState<string | null>(null);
  const [whatIfNote, setWhatIfNote] = useState<string | null>(null);

  useEffect(() => {
    api.skills().then((r) => {
      setSkills(r.skills);
      if (r.skills.length && !r.skills.find((s) => s.skill_id === skillId)) {
        setSkillId(r.skills[0].skill_id);
      }
    });
  }, []);

  async function onRank(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setNames({});
    setAuditStrip(null);
    setCeremony(false);
    setDecisionMsg(null);
    setWhatIfNote(null);
    setWhatIfLevel(level);
    try {
      const id = `ui-staff-${Date.now()}`;
      const ranked = await api.rank({
        request_id: id,
        required_skills: { [skillId]: level },
        shortlist_size: 3,
      });
      const next = { ...ranked, request_id: id };
      setResult(next);
      setDisplay(next);
      if (ranked.candidates[0]) setChosen(ranked.candidates[0].coded_identity);
      else setChosen("");
    } catch (err) {
      setResult(null);
      setDisplay(null);
      setError(err instanceof Error ? err.message : "Ranking failed");
    } finally {
      setBusy(false);
    }
  }

  async function onWhatIf(nextLevel: number) {
    setWhatIfLevel(nextLevel);
    if (!result) return;
    setBusy(true);
    setError(null);
    setWhatIfNote(`What-if re-rank at level ${nextLevel} (not persisted — decision uses original request).`);
    try {
      const id = `ui-whatif-${Date.now()}`;
      const ranked = await api.rank({
        request_id: id,
        required_skills: { [skillId]: nextLevel },
        shortlist_size: 3,
      });
      setDisplay({ ...ranked, request_id: id });
    } catch (err) {
      setError(err instanceof Error ? err.message : "What-if re-rank failed");
    } finally {
      setBusy(false);
    }
  }

  async function onResolve() {
    if (!result) return;
    setBusy(true);
    setError(null);
    try {
      if (!reduced) {
        setCeremony(true);
        await new Promise((r) => setTimeout(r, 520));
      }
      const res = await api.resolve({ request_id: result.request_id });
      setNames(resolvedMap(res.resolved));
      const stamp = new Date().toISOString();
      setAuditStrip(
        `AUDIT · resolve · request=${result.request_id} · identities=${res.resolved.length} · at ${stamp}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Resolve failed");
    } finally {
      setCeremony(false);
      setBusy(false);
    }
  }

  async function onDecision(e: FormEvent) {
    e.preventDefault();
    if (!result) return;
    setBusy(true);
    setError(null);
    setDecisionMsg(null);
    try {
      const body = {
        status: decisionStatus,
        chosen_coded_identity: chosen || undefined,
        rejection_reason: decisionStatus === "rejected" ? rejectionReason || undefined : undefined,
        override_note: decisionStatus === "overridden" ? overrideNote || undefined : undefined,
      };
      await api.decision(result.request_id, body);
      setDecisionMsg(`Decision recorded: ${decisionStatus}${chosen ? ` → ${chosen}` : ""}`);
      setAuditStrip(
        (prev) =>
          `${prev ? prev + " · " : ""}decision=${decisionStatus} · choice=${chosen || "none"} · ${new Date().toISOString()}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Decision failed");
    } finally {
      setBusy(false);
    }
  }

  const resolved = Object.keys(names).length > 0;
  const candidates = display?.candidates ?? [];
  const emptyAfterRank = result !== null && candidates.length === 0;

  return (
    <motion.div className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="panel">
        <h2 className="h2">Staff</h2>
        <p className="lede">Rank coded candidates against a required skill profile. Evidence is mandatory.</p>
        <NarrateBanner />
        <form onSubmit={onRank} style={{ borderTop: "1px solid var(--line)", paddingTop: "1.25rem" }}>
          <div className="form-row">
            <div className="field">
              <label htmlFor="skill">Skill</label>
              <select id="skill" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
                {skills.map((s) => (
                  <option key={s.skill_id} value={s.skill_id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="level">Required level</label>
              <select id="level" value={level} onChange={(e) => setLevel(Number(e.target.value))}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button className="btn" type="submit" disabled={busy}>
              {busy ? "Computing…" : "Rank shortlist"}
            </button>
            <button
              className="btn btn-amber"
              type="button"
              disabled={busy || !result?.candidates.length || resolved}
              onClick={onResolve}
            >
              Resolve names
            </button>
          </div>
        </form>

        <AnimatePresence>
          {ceremony ? (
            <motion.div
              key="ceremony"
              initial={reduced ? false : { opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: reduced ? 0.01 : 0.4 }}
              style={{
                marginTop: "1.25rem",
                padding: "1rem 1.15rem",
                border: "1px solid var(--teal-dim)",
                borderRadius: "var(--radius)",
                background: "rgba(45, 212, 191, 0.08)",
                fontFamily: "var(--font-display)",
                letterSpacing: "0.08em",
              }}
            >
              RESOLVING · identity gateway · audit trail opening…
            </motion.div>
          ) : null}
        </AnimatePresence>

        {auditStrip ? (
          <motion.div
            initial={reduced ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              marginTop: "1rem",
              fontSize: 12,
              fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
              color: "var(--teal)",
              letterSpacing: "0.02em",
              padding: "0.65rem 0.85rem",
              background: "rgba(45, 212, 191, 0.06)",
              borderLeft: "3px solid var(--teal)",
            }}
            role="status"
          >
            {auditStrip}
          </motion.div>
        ) : null}

        {error ? <p style={{ color: "var(--danger)", marginTop: "1rem" }}>{error}</p> : null}

        {result && !emptyAfterRank ? (
          <div style={{ marginTop: "1.75rem" }}>
            <div className="field" style={{ maxWidth: 360 }}>
              <label htmlFor="whatif">What-if required level (re-ranks, not persisted)</label>
              <input
                id="whatif"
                type="range"
                min={1}
                max={5}
                step={1}
                value={whatIfLevel}
                disabled={busy}
                onChange={(e) => onWhatIf(Number(e.target.value))}
              />
              <div style={{ fontSize: 13, color: "var(--ink-muted)" }}>Level {whatIfLevel}</div>
            </div>
            {whatIfNote ? (
              <p style={{ fontSize: 13, color: "var(--amber)", marginTop: "0.5rem" }}>{whatIfNote}</p>
            ) : null}
          </div>
        ) : null}

        <div style={{ marginTop: "2rem" }}>
          {!result ? (
            <p className="empty">No shortlist yet. Rank a skill profile to begin.</p>
          ) : emptyAfterRank ? (
            <p className="empty">
              Insufficient evidence — the engine returned no grounded candidates for this requirement.
            </p>
          ) : (
            <ShortlistReveal candidates={candidates} resolved={names} />
          )}
        </div>

        {resolved && result ? (
          <motion.form
            onSubmit={onDecision}
            initial={reduced ? false : { opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              marginTop: "2.5rem",
              paddingTop: "1.5rem",
              borderTop: "1px solid var(--line)",
            }}
          >
            <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 0.75rem" }}>Staffing decision</h3>
            <p style={{ color: "var(--ink-muted)", fontSize: 14, marginTop: 0 }}>
              Human oversight required. Accept, reject, or override with a chosen coded identity.
            </p>
            <div className="form-row">
              <div className="field">
                <label htmlFor="status">Status</label>
                <select
                  id="status"
                  value={decisionStatus}
                  onChange={(e) => setDecisionStatus(e.target.value as DecisionStatus)}
                >
                  <option value="accepted">Accept</option>
                  <option value="rejected">Reject</option>
                  <option value="overridden">Override</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="chosen">Chosen candidate</label>
                <select id="chosen" value={chosen} onChange={(e) => setChosen(e.target.value)}>
                  {(result.candidates.length ? result.candidates : display?.candidates ?? []).map((c) => (
                    <option key={c.coded_identity} value={c.coded_identity}>
                      {names[c.coded_identity] ?? c.coded_identity} (#{c.rank})
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {decisionStatus === "rejected" ? (
              <div className="field" style={{ marginBottom: "1rem" }}>
                <label htmlFor="rej">Rejection reason</label>
                <input
                  id="rej"
                  value={rejectionReason}
                  onChange={(e) => setRejectionReason(e.target.value)}
                  placeholder="Why this shortlist was rejected"
                />
              </div>
            ) : null}
            {decisionStatus === "overridden" ? (
              <div className="field" style={{ marginBottom: "1rem" }}>
                <label htmlFor="ovr">Override note</label>
                <input
                  id="ovr"
                  value={overrideNote}
                  onChange={(e) => setOverrideNote(e.target.value)}
                  placeholder="Why the engine rank was overridden"
                />
              </div>
            ) : null}
            <button className="btn" type="submit" disabled={busy || !chosen}>
              Record decision
            </button>
            {decisionMsg ? (
              <p style={{ color: "var(--teal)", marginTop: "0.85rem", fontSize: 14 }}>{decisionMsg}</p>
            ) : null}
          </motion.form>
        ) : null}
      </div>
    </motion.div>
  );
}
