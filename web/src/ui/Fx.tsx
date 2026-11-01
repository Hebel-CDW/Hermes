import { AnimatePresence, animate, motion, useReducedMotion } from "framer-motion";
import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

/** Motion is skipped in tests and for people who ask for less of it. */
const IS_TEST = import.meta.env.MODE === "test";
export function useCalm(): boolean {
  const reduce = useReducedMotion();
  return Boolean(reduce) || IS_TEST;
}

/** A number that counts up to its value. Shows the final value immediately when motion is off. */
export function CountUp({ value, digits = 0, suffix = "" }: { value: number; digits?: number; suffix?: string }) {
  const calm = useCalm();
  const [shown, setShown] = useState(calm ? value : 0);
  const from = useRef(calm ? value : 0);
  useEffect(() => {
    if (calm) {
      setShown(value);
      return;
    }
    const controls = animate(from.current, value, {
      duration: 0.9,
      ease: [0.22, 1, 0.36, 1],
      onUpdate: (v) => setShown(v),
      onComplete: () => {
        from.current = value;
      },
    });
    return () => controls.stop();
  }, [value, calm]);
  return (
    <span className="num">
      {shown.toFixed(digits)}
      {suffix}
    </span>
  );
}

/** Children rise in one after another. */
export function Stagger({ children, className, gap = 0.06 }: { children: ReactNode; className?: string; gap?: number }) {
  const calm = useCalm();
  return (
    <motion.div
      className={className}
      initial={calm ? false : "hidden"}
      animate="show"
      variants={{ hidden: {}, show: { transition: { staggerChildren: gap } } }}
    >
      {children}
    </motion.div>
  );
}

export function Rise({ children, className }: { children: ReactNode; className?: string }) {
  const calm = useCalm();
  return (
    <motion.div
      className={className}
      variants={calm ? undefined : { hidden: { opacity: 0, y: 14 }, show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] } } }}
    >
      {children}
    </motion.div>
  );
}

const CONFETTI = ["#b5122b", "#004a5d", "#0f6b4f", "#e0566b", "#92400e"];

/** A short celebratory burst. Render it with a changing `fire` key to trigger it. */
export function Burst({ fire }: { fire: number }) {
  const calm = useCalm();
  if (calm || fire === 0) return null;
  return (
    <div className="burst" aria-hidden key={fire}>
      {Array.from({ length: 26 }, (_, i) => {
        const angle = (i / 26) * Math.PI * 2 + (i % 3) * 0.2;
        const dist = 90 + (i % 5) * 28;
        return (
          <motion.i
            key={i}
            style={{ background: CONFETTI[i % CONFETTI.length] }}
            initial={{ x: 0, y: 0, scale: 0.4, opacity: 1, rotate: 0 }}
            animate={{ x: Math.cos(angle) * dist, y: Math.sin(angle) * dist + 40, scale: 1, opacity: 0, rotate: 240 + i * 20 }}
            transition={{ duration: 1.1 + (i % 4) * 0.12, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}
    </div>
  );
}

export type Toast = { id: number; text: string; tone: "ok" | "info" | "warn" };

/** Tiny toast stack. `push` returns nothing; toasts remove themselves. */
export function useToasts() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const next = useRef(1);
  const push = useCallback((text: string, tone: Toast["tone"] = "ok") => {
    const id = next.current++;
    setToasts((t) => [...t.slice(-3), { id, text, tone }]);
    if (!IS_TEST) setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const host = (
    <div className="toasts" role="status" aria-live="polite">
      <AnimatePresence>
        {toasts.map((t) => (
          <motion.div
            key={t.id}
            className={`toast toast-${t.tone}`}
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.22 }}
          >
            {t.text}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  );
  return { push, host };
}

/** Progress ring that sweeps to its value. `value` is a plain 0..1 fraction. */
export function GoalRing({ value, size = 132, label, sub }: { value: number; size?: number; label: string; sub?: string }) {
  const calm = useCalm();
  const r = size / 2 - 9;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${Math.round(v * 100)}%`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-sunk)" strokeWidth="9" />
      <motion.circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="var(--crimson)"
        strokeWidth="9"
        strokeLinecap="round"
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
        strokeDasharray={c}
        initial={{ strokeDashoffset: calm ? c * (1 - v) : c }}
        animate={{ strokeDashoffset: c * (1 - v) }}
        transition={{ duration: calm ? 0 : 1.1, ease: [0.22, 1, 0.36, 1] }}
      />
      <text x="50%" y={sub ? "46%" : "50%"} textAnchor="middle" dominantBaseline="central" fontSize={size / 4.4} fontWeight={650} fill="var(--ink)">
        {Math.round(v * 100)}%
      </text>
      {sub && (
        <text x="50%" y="64%" textAnchor="middle" dominantBaseline="central" fontSize={size / 10} fill="var(--ink-3)">
          {sub}
        </text>
      )}
    </svg>
  );
}

export type RadarSeries = { name: string; color: string; values: number[] };

/** Radar chart on a 0..max scale. `required` draws the role's target as a dashed outline. */
export function Radar({
  axes,
  series,
  required,
  max = 5,
  size = 340,
}: {
  axes: string[];
  series: RadarSeries[];
  required?: number[];
  max?: number;
  size?: number;
}) {
  const calm = useCalm();
  const cx = size / 2;
  const cy = size / 2;
  const R = size / 2 - 58;
  const n = axes.length;
  const pt = (i: number, v: number) => {
    const a = -Math.PI / 2 + (i / n) * Math.PI * 2;
    const rr = (Math.max(0, Math.min(max, v)) / max) * R;
    return [cx + Math.cos(a) * rr, cy + Math.sin(a) * rr] as const;
  };
  const poly = (vals: number[]) => vals.map((v, i) => pt(i, v).join(",")).join(" ");
  if (n < 3) {
    return <p className="muted">Pick a role with at least three skills to draw the shape.</p>;
  }
  return (
    <svg className="radar" width="100%" viewBox={`-80 0 ${size + 160} ${size}`} role="img" aria-label={`Skill levels by person across ${n} skills`}>
      {[1, 2, 3, 4, 5].map((ring) => (
        <polygon key={ring} points={poly(axes.map(() => (ring / 5) * max))} fill="none" stroke="var(--hairline)" strokeWidth={ring === 5 ? 1.2 : 0.8} />
      ))}
      {axes.map((_, i) => {
        const [x, y] = pt(i, max);
        return <line key={i} x1={cx} y1={cy} x2={x} y2={y} stroke="var(--hairline)" />;
      })}
      {required && <polygon points={poly(required)} fill="none" stroke="var(--ink-3)" strokeWidth="1.4" strokeDasharray="5 4" />}
      {series.map((s, k) => (
        <motion.polygon
          key={s.name}
          points={poly(s.values)}
          fill={s.color}
          fillOpacity={0.16}
          stroke={s.color}
          strokeWidth="2"
          strokeLinejoin="round"
          style={{ transformBox: "fill-box", transformOrigin: "center" }}
          initial={calm ? false : { opacity: 0, scale: 0.2 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, delay: k * 0.12, ease: [0.22, 1, 0.36, 1] }}
        />
      ))}
      {axes.map((a, i) => {
        const [x, y] = pt(i, max * 1.2);
        const anchor = x < cx - 6 ? "end" : x > cx + 6 ? "start" : "middle";
        return (
          <text key={a} x={x} y={y} textAnchor={anchor} dominantBaseline="central" fontSize="11" fill="var(--ink-2)">
            {a.length > 26 ? `${a.slice(0, 25)}…` : a}
          </text>
        );
      })}
    </svg>
  );
}

/** Heat colour for a 0..5 level, matching the app's level palette. */
export const LEVEL_COLOR: Record<number, string> = {
  0: "transparent",
  1: "var(--lvl-1)",
  2: "var(--lvl-2)",
  3: "var(--lvl-3)",
  4: "var(--lvl-4)",
  5: "var(--lvl-5)",
};
