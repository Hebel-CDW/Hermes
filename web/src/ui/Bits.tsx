import type { ReactNode } from "react";
import { pct } from "../lib/format";

/** A proportion bar. `value` is a backend ratio in [0,1]; null renders an empty track. */
export function Bar({ value, tone }: { value: number | null | undefined; tone?: "crimson" | "ink" }) {
  const w = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value)) * 100;
  return (
    <div className={`bar ${tone ?? ""}`} role="presentation">
      <span style={{ width: `${w}%` }} />
    </div>
  );
}

export function Metric({ label, value, tone }: { label: string; value: number | null | undefined; tone?: "crimson" | "ink" }) {
  return (
    <div className="metric-row">
      <span className="ink-2">{label}</span>
      <span className="num">{pct(value)}</span>
      <Bar value={value} tone={tone} />
    </div>
  );
}

export function Levels({ level, required }: { level: number | null | undefined; required?: boolean }) {
  return (
    <span className={`levels ${required ? "req" : ""}`} aria-label={level ? `Level ${level} of 5` : "No level"}>
      {[1, 2, 3, 4, 5].map((n) => (
        <i key={n} className={level && n <= level ? "on" : ""} />
      ))}
    </span>
  );
}

export function Kpi({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="kpi">
      <div className="label">{label}</div>
      <div className="kpi-value">{value}</div>
      {note && <div className="kpi-note">{note}</div>}
    </div>
  );
}

export function PageHead({
  trail,
  title,
  lede,
  aside,
}: {
  trail: string[];
  title: ReactNode;
  lede?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <header className="page-head">
      <div style={{ minWidth: 0 }}>
        <div className="eyebrow">
          {trail.map((t, i) => (
            <span key={t} className="label">
              {i > 0 && <span style={{ marginRight: 8 }}>/</span>}
              {t}
            </span>
          ))}
        </div>
        <h1>{title}</h1>
        {lede && <p>{lede}</p>}
      </div>
      {aside}
    </header>
  );
}

const STATUS_TONE: Record<string, string> = {
  open: "chip-teal",
  accepted: "chip-ok",
  overridden: "chip-warn",
  rejected: "chip-crimson",
};

export function StatusChip({ status }: { status: string | null | undefined }) {
  if (!status) return <span className="chip">Pending</span>;
  return <span className={`chip ${STATUS_TONE[status] ?? ""}`}>{status[0].toUpperCase() + status.slice(1)}</span>;
}

/** Ring showing a backend ratio. Purely presentational. */
export function Ring({ value, size = 120, label }: { value: number | null | undefined; size?: number; label: string }) {
  const r = size / 2 - 8;
  const c = 2 * Math.PI * r;
  const v = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value));
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`${label}: ${pct(value)}`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#F1F3F5" strokeWidth="8" />
      <circle
        cx={size / 2}
        cy={size / 2}
        r={r}
        fill="none"
        stroke="#B5122B"
        strokeWidth="8"
        strokeDasharray={`${c * v} ${c}`}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" fontSize={size / 5.5} fontWeight={600} fill="#0F172A">
        {pct(value, 0)}
      </text>
    </svg>
  );
}
