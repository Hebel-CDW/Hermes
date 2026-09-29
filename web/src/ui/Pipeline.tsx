import type { DataQuality } from "../api/types";
import { int } from "../lib/format";

/**
 * Imported → Validated → Mapped → Pending → Scored, exactly as reported by /api/data-quality.
 * A null stage (no workbook ingestion recorded) renders "—", never a guessed number.
 */
export function PipelineStates({ dq }: { dq: DataQuality }) {
  const p = dq.pipeline;
  const stages: [string, number | null, string][] = [
    ["Imported", p.imported, "coded identities"],
    ["Validated", p.validated, "accepted cells"],
    ["Mapped", p.mapped, "governed labels"],
    ["Pending", p.pending, "labels awaiting approval"],
    ["Scored", p.scored, "identities with evidence"],
  ];
  return (
    <section className="pipeline-states" aria-label="Data pipeline states">
      {stages.map(([label, value, note]) => (
        <div
          key={label}
          className={`pipeline-state ${value === 0 && (label === "Scored" || label === "Mapped") ? "zero" : ""}`}
          data-testid={`pipeline-${label.toLowerCase()}`}
        >
          <div className="label">{label}</div>
          <div className="v">{value === null ? "—" : int(value)}</div>
          <div className="n">{note}</div>
        </div>
      ))}
    </section>
  );
}
