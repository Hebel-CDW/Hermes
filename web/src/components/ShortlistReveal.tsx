import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import type { RankedCandidate, Resolved, SkillReasoningDetail } from "../api/client";
import { itemUp, stagger } from "../motion/presets";
import { ScoreMeter } from "./ScoreMeter";

type Props = {
  candidates: RankedCandidate[];
  resolved?: Record<string, string>;
};

function isSkillDetail(v: unknown): v is SkillReasoningDetail {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

function SkillDrillDown({
  skill,
  detail,
  summary,
  reduced,
}: {
  skill: string;
  detail: SkillReasoningDetail | undefined;
  summary: string;
  reduced: boolean | null;
}) {
  const [open, setOpen] = useState(false);
  const hasDetail = detail && detail.status !== "missing";
  return (
    <li style={{ marginBottom: 8 }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        style={{
          background: "none",
          border: "none",
          padding: 0,
          color: "inherit",
          textAlign: "left",
          width: "100%",
          font: "inherit",
          cursor: "pointer",
        }}
      >
        <strong style={{ color: "var(--ink)" }}>{skill}</strong>
        <span style={{ color: "var(--ink-muted)" }}> — {summary}</span>
        <span style={{ marginLeft: 8, fontSize: 11, color: "var(--teal)", letterSpacing: "0.06em" }}>
          {open ? "HIDE" : "DETAIL"}
        </span>
      </button>
      <AnimatePresence initial={false}>
        {open ? (
          <motion.div
            key="drill"
            initial={reduced ? false : { opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, height: 0 }}
            transition={{ duration: reduced ? 0.01 : 0.28 }}
            style={{ overflow: "hidden" }}
          >
            <div
              style={{
                marginTop: 8,
                padding: "0.75rem 0.9rem",
                background: "rgba(232,238,244,0.04)",
                borderLeft: "2px solid var(--teal-dim)",
                fontSize: 13,
                color: "var(--ink-muted)",
                display: "grid",
                gap: 6,
              }}
            >
              {!hasDetail ? (
                <span>Insufficient evidence for this skill.</span>
              ) : (
                <>
                  <div>
                    Level <strong style={{ color: "var(--ink)" }}>{detail.level ?? "—"}</strong>
                    {detail.required != null ? ` / required ${detail.required}` : ""}
                  </div>
                  <div>
                    Confidence{" "}
                    <strong style={{ color: "var(--ink)" }}>
                      {detail.confidence != null ? detail.confidence.toFixed(2) : "—"}
                    </strong>
                  </div>
                  <div>
                    Volume{" "}
                    <strong style={{ color: "var(--ink)" }}>
                      {detail.volume_score != null ? detail.volume_score.toFixed(2) : "—"}
                    </strong>
                  </div>
                  <div>
                    Freshness{" "}
                    <strong style={{ color: "var(--ink)" }}>
                      {detail.freshness != null ? detail.freshness.toFixed(2) : "—"}
                    </strong>
                  </div>
                  <div>
                    Evidence:{" "}
                    {(detail.evidence_ids && detail.evidence_ids.length
                      ? detail.evidence_ids
                      : []
                    ).join(", ") || "—"}
                  </div>
                </>
              )}
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </li>
  );
}

export function ShortlistReveal({ candidates, resolved = {} }: Props) {
  const reduced = useReducedMotion();
  if (!candidates.length) {
    return (
      <p className="empty">
        No grounded recommendation available from the fitness engine. Insufficient evidence across
        the pilot cohort for this profile.
      </p>
    );
  }
  return (
    <motion.ol
      variants={stagger}
      initial="initial"
      animate="animate"
      style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "1rem" }}
    >
      {candidates.map((c) => {
        const name = resolved[c.coded_identity];
        const detail = c.reasoning_detail ?? {};
        return (
          <motion.li
            key={c.coded_identity}
            variants={itemUp}
            style={{
              borderTop: "1px solid var(--line)",
              padding: "1.1rem 0 0.4rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "1rem", alignItems: "baseline" }}>
              <div>
                <div style={{ fontSize: 12, color: "var(--ink-muted)", letterSpacing: "0.08em" }}>
                  RANK {c.rank}
                </div>
                <AnimatePresence mode="wait">
                  <motion.div
                    key={name ?? c.coded_identity}
                    initial={reduced ? false : { opacity: 0, filter: "blur(6px)" }}
                    animate={{ opacity: 1, filter: "blur(0px)" }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: reduced ? 0.01 : 0.45 }}
                    style={{
                      fontFamily: "var(--font-display)",
                      fontSize: "1.45rem",
                      fontWeight: 700,
                      marginTop: 4,
                    }}
                  >
                    {name ?? c.coded_identity}
                  </motion.div>
                </AnimatePresence>
                {name ? (
                  <div style={{ fontSize: 13, color: "var(--teal)", marginTop: 2 }}>{c.coded_identity}</div>
                ) : null}
              </div>
              <div style={{ minWidth: 160, flex: "0 0 180px" }}>
                <ScoreMeter score={c.fitness_score} label="Fitness" />
              </div>
            </div>
            <ul style={{ margin: "0.85rem 0 0", padding: 0, listStyle: "none", color: "var(--ink-muted)", fontSize: 14 }}>
              {Object.entries(c.per_skill_reasoning).map(([skill, reason]) => {
                const raw = detail[skill];
                return (
                  <SkillDrillDown
                    key={skill}
                    skill={skill}
                    detail={isSkillDetail(raw) ? raw : undefined}
                    summary={reason}
                    reduced={reduced}
                  />
                );
              })}
            </ul>
            <div style={{ fontSize: 12, color: "var(--ink-muted)", marginTop: 6 }}>
              evidence: {c.evidence_ids.join(", ") || "—"}
            </div>
          </motion.li>
        );
      })}
    </motion.ol>
  );
}

export function resolvedMap(items: Resolved[]): Record<string, string> {
  return Object.fromEntries(items.map((r) => [r.coded_identity, r.display_name]));
}
