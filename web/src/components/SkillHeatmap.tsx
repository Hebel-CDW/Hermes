import type { CSSProperties } from "react";
import { motion } from "framer-motion";
import { itemUp, stagger } from "../motion/presets";

type Cell = {
  coded_identity: string;
  skill_id: string;
  proficiency: number;
  freshness: number;
};

export function SkillHeatmap({ rows }: { rows: Cell[] }) {
  const skills = Array.from(new Set(rows.map((r) => r.skill_id))).sort();
  const ids = Array.from(new Set(rows.map((r) => r.coded_identity))).sort();
  const map = new Map(rows.map((r) => [`${r.coded_identity}:${r.skill_id}`, r]));

  return (
    <div style={{ overflowX: "auto" }}>
      <motion.table
        variants={stagger}
        initial="initial"
        animate="animate"
        style={{ borderCollapse: "collapse", width: "100%", minWidth: 520 }}
      >
        <thead>
          <tr>
            <th style={th}>Coded ID</th>
            {skills.map((s) => (
              <th key={s} style={th}>
                {s.replace(/_/g, " ")}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {ids.map((id) => (
            <motion.tr key={id} variants={itemUp}>
              <td style={td}>{id}</td>
              {skills.map((s) => {
                const cell = map.get(`${id}:${s}`);
                const alpha = cell ? 0.15 + cell.proficiency * 0.15 : 0.04;
                return (
                  <td key={s} style={{ ...td, background: `rgba(45, 212, 191, ${alpha})`, textAlign: "center" }}>
                    {cell ? (
                      <motion.span initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
                        L{cell.proficiency}
                        <span style={{ display: "block", fontSize: 11, color: "var(--ink-muted)" }}>
                          f {cell.freshness.toFixed(2)}
                        </span>
                      </motion.span>
                    ) : (
                      "—"
                    )}
                  </td>
                );
              })}
            </motion.tr>
          ))}
        </tbody>
      </motion.table>
    </div>
  );
}

const th: CSSProperties = {
  textAlign: "left",
  fontSize: 11,
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--ink-muted)",
  padding: "0.55rem",
  borderBottom: "1px solid var(--line)",
};

const td: CSSProperties = {
  padding: "0.65rem 0.55rem",
  borderBottom: "1px solid var(--line)",
  fontSize: 13,
};
