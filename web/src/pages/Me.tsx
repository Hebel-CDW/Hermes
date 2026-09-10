import { FormEvent, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { api, ensureAuth, MeResult } from "../api/client";
import { NarrateBanner } from "../components/NarrateBanner";
import { itemUp, pageVariants, stagger } from "../motion/presets";

export function Me() {
  const [me, setMe] = useState<MeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState("");
  const [skillId, setSkillId] = useState("");
  const [contestMsg, setContestMsg] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        // Manager token first to list identities, then subject token for /me
        await ensureAuth({ force: true });
        const { identities } = await api.identities();
        const coded = identities[0];
        if (!coded) throw new Error("No identities available for demo subject view");
        await ensureAuth({
          force: true,
          sub: coded,
          roles: ["subject"],
          coded_identity: coded,
        });
        const profile = await api.me();
        if (!cancelled) {
          setMe(profile);
          if (profile.skills[0]) setSkillId(profile.skills[0].skill_id);
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load /me");
      }
    })();
    return () => {
      cancelled = true;
      // Restore manager JWT so Staff/Matrix keep working after leaving /me
      void ensureAuth({ force: true }).catch(() => undefined);
    };
  }, []);

  async function onContest(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim()) return;
    setBusy(true);
    setError(null);
    setContestMsg(null);
    try {
      if (me?.coded_identity) {
        await ensureAuth({
          force: true,
          sub: me.coded_identity,
          roles: ["subject"],
          coded_identity: me.coded_identity,
        });
      }
      const res = await api.contest({
        reason: reason.trim(),
        skill_id: skillId || undefined,
      });
      setContestMsg(`Contest ${res.contest_id} opened (${res.status}).`);
      setReason("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Contest failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div className="page" variants={pageVariants} initial="initial" animate="animate" exit="exit">
      <div className="panel">
        <h2 className="h2">Me</h2>
        <p className="lede">Subject evidence view and contest flow (demo token with coded_identity).</p>
        <NarrateBanner>
          Contests are logged to the audit ledger. This demo issues a subject JWT from the first coded identity.
        </NarrateBanner>
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {!me && !error ? <p className="empty">Loading your evidence…</p> : null}

        {me ? (
          <motion.div variants={stagger} initial="initial" animate="animate">
            <motion.div variants={itemUp} style={{ marginBottom: "1.75rem" }}>
              <div style={{ fontSize: 12, letterSpacing: "0.08em", color: "var(--ink-muted)" }}>CODED IDENTITY</div>
              <div style={{ fontFamily: "var(--font-display)", fontSize: "1.6rem", fontWeight: 700 }}>
                {me.coded_identity}
              </div>
            </motion.div>

            <motion.div variants={itemUp} style={{ marginBottom: "2rem" }}>
              <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 0.85rem" }}>Skills on record</h3>
              {!me.skills.length ? (
                <p className="empty">No skills matrix rows for this identity.</p>
              ) : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {me.skills.map((s) => (
                    <li
                      key={s.skill_id}
                      style={{
                        borderTop: "1px solid var(--line)",
                        padding: "0.75rem 0",
                        display: "flex",
                        justifyContent: "space-between",
                        gap: "1rem",
                        flexWrap: "wrap",
                        fontSize: 14,
                      }}
                    >
                      <strong>{s.skill_id}</strong>
                      <span style={{ color: "var(--ink-muted)" }}>
                        L{s.proficiency} · conf {s.confidence.toFixed(2)} · fresh {s.freshness.toFixed(2)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </motion.div>

            <motion.div variants={itemUp} style={{ marginBottom: "2rem" }}>
              <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 0.85rem" }}>Evidence</h3>
              {!me.evidence.length ? (
                <p className="empty">No evidence artifacts linked.</p>
              ) : (
                <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                  {me.evidence.map((e) => (
                    <li
                      key={e.evidence_id}
                      style={{
                        borderTop: "1px solid var(--line)",
                        padding: "0.85rem 0",
                        fontSize: 14,
                      }}
                    >
                      <div style={{ fontFamily: "var(--font-display)" }}>{e.evidence_id}</div>
                      <div style={{ color: "var(--ink-muted)", marginTop: 4 }}>
                        {e.skill_id} · {e.evidence_type} · {e.source_ref} · {e.occurred_at}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </motion.div>

            <motion.form variants={itemUp} onSubmit={onContest}>
              <h3 style={{ fontFamily: "var(--font-display)", margin: "0 0 0.75rem" }}>Contest evidence</h3>
              <div className="form-row">
                <div className="field">
                  <label htmlFor="contest-skill">Skill (optional)</label>
                  <select id="contest-skill" value={skillId} onChange={(e) => setSkillId(e.target.value)}>
                    <option value="">—</option>
                    {me.skills.map((s) => (
                      <option key={s.skill_id} value={s.skill_id}>
                        {s.skill_id}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="contest-reason">Reason</label>
                  <input
                    id="contest-reason"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Describe the contest"
                    required
                  />
                </div>
              </div>
              <button className="btn" type="submit" disabled={busy || !reason.trim()}>
                {busy ? "Submitting…" : "Open contest"}
              </button>
              {contestMsg ? (
                <p style={{ color: "var(--teal)", marginTop: "0.85rem", fontSize: 14 }}>{contestMsg}</p>
              ) : null}
            </motion.form>
          </motion.div>
        ) : null}
      </div>
    </motion.div>
  );
}
