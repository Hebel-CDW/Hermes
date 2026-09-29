/** Presentation-only formatting. Values are displayed, never recomputed. */
export const pct = (v: number | null | undefined, digits = 1): string =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(digits)}%`;

export const fixed = (v: number | null | undefined, digits = 4): string =>
  v === null || v === undefined ? "—" : v.toFixed(digits);

export const int = (v: number | null | undefined): string =>
  v === null || v === undefined ? "—" : v.toLocaleString("en-US");

export const EXCLUSION_TEXT: Record<string, string> = {
  no_evidence_on_any_required_skill: "No evidence on any required skill",
  below_min_coverage: "Required-skill coverage below threshold",
  missing_critical_skill: "Missing a critical skill",
};

export const exclusionText = (reason: string): string => EXCLUSION_TEXT[reason] ?? reason;

/** Skill ids are engine keys; show a readable label. Prefer an API name when one is passed. */
export const humanSkill = (id: string, names?: Record<string, string>): string => {
  if (names?.[id]) return names[id];
  return id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

export const shortTime = (iso: string | null | undefined): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toISOString().replace("T", " ").slice(0, 16) + " UTC";
};

export const REJECTION_TEXT: Record<string, string> = {
  non_numeric_cell: "Invalid value (text)",
  missing_name: "Missing person",
  fractional_average: "Group average value",
  group_or_section_header: "Group average row",
  section_header: "Section header",
  out_of_range_value: "Out of range",
  unparseable_value: "Unparseable value",
  deferred_to_cert_workstream: "Certificate workstream",
};

export const rejectionText = (code: string): string => REJECTION_TEXT[code] ?? code;
