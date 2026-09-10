import { motion, useReducedMotion } from "framer-motion";

export function ScoreMeter({ score, label }: { score: number; label?: string }) {
  const reduced = useReducedMotion();
  const pct = Math.max(0, Math.min(100, Math.round(score * 100)));
  return (
    <div style={{ width: "100%" }}>
      {label ? (
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6, fontSize: 13 }}>
          <span style={{ color: "var(--ink-muted)" }}>{label}</span>
          <span style={{ color: "var(--teal)", fontWeight: 600 }}>{pct}%</span>
        </div>
      ) : null}
      <div
        style={{
          height: 8,
          borderRadius: 999,
          background: "rgba(232,238,244,0.08)",
          overflow: "hidden",
        }}
      >
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={reduced ? { duration: 0.01 } : { duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
          style={{
            height: "100%",
            borderRadius: 999,
            background: "linear-gradient(90deg, var(--teal-dim), var(--teal))",
          }}
        />
      </div>
    </div>
  );
}
