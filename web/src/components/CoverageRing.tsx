import { motion, useReducedMotion } from "framer-motion";

export function CoverageRing({ pct }: { pct: number }) {
  const reduced = useReducedMotion();
  const r = 54;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  const offset = c - (clamped / 100) * c;
  return (
    <div style={{ display: "grid", placeItems: "center", position: "relative", width: 160, height: 160 }}>
      <svg width="160" height="160" viewBox="0 0 140 140" aria-hidden>
        <circle cx="70" cy="70" r={r} fill="none" stroke="rgba(232,238,244,0.08)" strokeWidth="10" />
        <motion.circle
          cx="70"
          cy="70"
          r={r}
          fill="none"
          stroke="var(--teal)"
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: offset }}
          transition={reduced ? { duration: 0.01 } : { duration: 1.1, ease: [0.22, 1, 0.36, 1] }}
          transform="rotate(-90 70 70)"
        />
      </svg>
      <div style={{ position: "absolute", textAlign: "center" }}>
        <div style={{ fontFamily: "var(--font-display)", fontSize: "1.8rem", fontWeight: 800 }}>{clamped.toFixed(0)}%</div>
        <div style={{ fontSize: 12, color: "var(--ink-muted)", letterSpacing: "0.08em" }}>COVERAGE</div>
      </div>
    </div>
  );
}
