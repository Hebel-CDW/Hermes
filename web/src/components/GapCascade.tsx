import { motion } from "framer-motion";
import type { GapItem } from "../api/client";
import { itemUp, stagger } from "../motion/presets";

export function GapCascade({ gaps }: { gaps: GapItem[] }) {
  if (!gaps.length) {
    return <p className="empty">No grounded gaps returned by the engine.</p>;
  }
  const max = Math.max(...gaps.map((g) => g.demand_impact), 0.001);
  return (
    <motion.ul variants={stagger} initial="initial" animate="animate" style={{ listStyle: "none", margin: 0, padding: 0 }}>
      {gaps.map((g) => (
        <motion.li key={g.skill_id} variants={itemUp} style={{ marginBottom: "1.25rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
            <strong>{g.skill_id}</strong>
            <span style={{ color: "var(--amber)" }}>impact {g.demand_impact.toFixed(2)}</span>
          </div>
          <div style={{ height: 10, borderRadius: 999, background: "rgba(232,238,244,0.08)", overflow: "hidden" }}>
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${(g.demand_impact / max) * 100}%` }}
              transition={{ duration: 0.85, ease: [0.22, 1, 0.36, 1] }}
              style={{ height: "100%", background: "linear-gradient(90deg, var(--amber-dim), var(--amber))" }}
            />
          </div>
          <p style={{ margin: "0.45rem 0 0", color: "var(--ink-muted)", fontSize: 14 }}>{g.reasoning}</p>
        </motion.li>
      ))}
    </motion.ul>
  );
}
