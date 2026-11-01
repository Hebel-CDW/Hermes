import type { ExcludedCandidate, RankedCandidate, SkillContribution } from "../api/types";
import { pct } from "./format";

/**
 * Plain-English explanations built ONLY from values the engine already returned.
 * Nothing here recomputes a score; it turns numbers into sentences a manager can repeat.
 */

export type Tone = "good" | "warn" | "bad" | "neutral";
type NameOf = (id: string) => string;

export const LEVEL_NAMES = ["No level", "Awareness", "Working", "Proficient", "Advanced", "Expert"];
export const levelName = (l: number | null | undefined): string => (l ? `${LEVEL_NAMES[l] ?? l} (L${l})` : "none");

export function freshnessWords(f: number | null): string {
  if (f === null) return "no dated proof";
  if (f >= 0.8) return "recent";
  if (f >= 0.5) return "fairly recent";
  if (f >= 0.25) return "getting old";
  return "old and fading";
}

/** Confidence is agreement across KINDS of proof (tickets, certificate, manager sign-off). */
export function confidenceWords(c: number | null): { label: string; tone: Tone; text: string } {
  if (c === null) return { label: "No proof", tone: "bad", text: "There is no proof on file for this skill." };
  if (c >= 0.85)
    return { label: "Very sure", tone: "good", text: "Different kinds of proof agree, for example real tickets and a certificate." };
  if (c >= 0.6) return { label: "Fairly sure", tone: "good", text: "Two kinds of proof point the same way." };
  return { label: "Limited proof", tone: "warn", text: "Only one kind of proof exists, such as tickets alone. A certificate or manager sign-off would raise it." };
}

/** Count what the evidence ids tell us about the kinds of proof behind a skill. */
export function evidenceMix(ids: string[]): { tickets: number; certificates: number; declared: number } {
  let tickets = 0;
  let certificates = 0;
  let declared = 0;
  for (const id of ids) {
    if (id.startsWith("cert-")) certificates += 1;
    else if (id.startsWith("decl-") || id.startsWith("mgr-decl-") || id.startsWith("wb-")) declared += 1;
    else tickets += 1;
  }
  return { tickets, certificates, declared };
}

export function mixWords(ids: string[]): string {
  const m = evidenceMix(ids);
  const parts: string[] = [];
  if (m.tickets) parts.push(`${m.tickets} ticket${m.tickets === 1 ? "" : "s"}`);
  if (m.certificates) parts.push(`${m.certificates} certificate${m.certificates === 1 ? "" : "s"}`);
  if (m.declared) parts.push(`${m.declared} manager-confirmed claim${m.declared === 1 ? "" : "s"}`);
  return parts.length ? parts.join(" and ") : "no proof";
}

export function skillLine(skill: string, s: SkillContribution, nameOf: NameOf): string {
  const name = nameOf(skill);
  if (s.status === "missing") return `${name}: no proof on file (the role needs level ${s.required_level}).`;
  if (s.status === "adjacent")
    return `${name}: no direct proof, but ${s.adjacency_source_skill ? nameOf(s.adjacency_source_skill) : "a closely related skill"} counts for part of it (${pct(s.adjacency_discount, 0)} credit).`;
  return `${name}: level ${s.actual_level} against the ${s.required_level} needed, from ${mixWords(s.evidence_ids)}. The proof is ${freshnessWords(s.freshness)}.`;
}

export type Story = {
  covered: string[];
  short: string[];
  partial: string[];
  missing: string[];
  matched: number;
  required: number;
  meanConfidence: number | null;
  meanFreshness: number | null;
};

export function story(c: RankedCandidate, nameOf: NameOf): Story {
  const covered: string[] = [];
  const short: string[] = [];
  const partial: string[] = [];
  const missing: string[] = [];
  const conf: number[] = [];
  const fresh: number[] = [];
  for (const [skill, s] of Object.entries(c.reasoning_detail)) {
    if (s.status === "missing") missing.push(skillLine(skill, s, nameOf));
    else if (s.status === "adjacent") partial.push(skillLine(skill, s, nameOf));
    else {
      (s.actual_level ?? 0) >= (s.required_level ?? 0) ? covered.push(skillLine(skill, s, nameOf)) : short.push(skillLine(skill, s, nameOf));
      if (s.confidence !== null) conf.push(s.confidence);
      if (s.freshness !== null) fresh.push(s.freshness);
    }
  }
  const mean = (a: number[]) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
  return {
    covered,
    short,
    partial,
    missing,
    matched: c.calculation?.matched_skill_count ?? covered.length + short.length,
    required: c.calculation?.required_skill_count ?? Object.keys(c.reasoning_detail).length,
    meanConfidence: mean(conf),
    meanFreshness: mean(fresh),
  };
}

export type Verdict = { tone: Tone; title: string; body: string };

/** The one-sentence answer a manager needs first. */
export function verdict(cands: RankedCandidate[], nameOf: (coded: string) => string): Verdict {
  if (cands.length === 0)
    return {
      tone: "bad",
      title: "No one fits this role right now",
      body: "Nobody has enough proof of the required skills. The reasons are listed under Not a fit this time. To fill the role, grow someone into it from the Learning page or widen the skills required.",
    };
  const [a, b] = cands;
  const an = nameOf(a.coded_identity);
  if (!b)
    return {
      tone: "warn",
      title: `${an} is the only person who qualifies`,
      body: `No one else has enough proof for this role. That makes ${an} a single point of failure: if they are unavailable there is no backup.`,
    };
  const gap = a.fitness_score - b.fitness_score;
  const rel = a.fitness_score > 0 ? gap / a.fitness_score : 0;
  const bn = nameOf(b.coded_identity);
  if (rel < 0.05)
    return {
      tone: "warn",
      title: `Too close to call: ${an} and ${bn}`,
      body: `Their fit scores are ${a.fitness_score.toFixed(3)} and ${b.fitness_score.toFixed(3)}, a difference of ${gap.toFixed(3)}. The numbers do not separate them, so use judgement: compare the kind and age of their proof below, then decide.`,
    };
  if (rel >= 0.45)
    return {
      tone: "good",
      title: `${an} is the clear first choice`,
      body: `${an} scores ${pct(a.fitness_score)} against ${pct(b.fitness_score)} for ${bn}, who is next. ${an} has stronger and better-evidenced proof on the skills this role needs.`,
    };
  return {
    tone: "neutral",
    title: `${an} leads, ${bn} is a credible alternative`,
    body: `${an} scores ${pct(a.fitness_score)} and ${bn} ${pct(b.fitness_score)}. The lead is real but not large, so check the differences below before you decide.`,
  };
}

/** Why #1 is ahead of somebody else, skill by skill, using the engine's own contributions. */
export function whyNotAhead(top: RankedCandidate, other: RankedCandidate, topName: string, otherName: string, nameOf: NameOf): string[] {
  const lines: string[] = [];
  const skills = new Set([...Object.keys(top.reasoning_detail), ...Object.keys(other.reasoning_detail)]);
  const diffs = [...skills]
    .map((k) => ({ k, t: top.reasoning_detail[k], o: other.reasoning_detail[k] }))
    .filter((x) => x.t && x.o)
    .map((x) => ({ ...x, d: (x.t.contribution ?? 0) - (x.o.contribution ?? 0) }))
    .sort((p, q) => Math.abs(q.d) - Math.abs(p.d))
    .slice(0, 3);
  for (const { k, t, o, d } of diffs) {
    const name = nameOf(k);
    if (Math.abs(d) < 0.005) continue;
    if (o.status === "missing") lines.push(`${otherName} has no proof of ${name}; ${topName} does (level ${t.actual_level}).`);
    else if (t.status === "missing") lines.push(`${topName} has no proof of ${name}, while ${otherName} does (level ${o.actual_level}).`);
    else if ((o.actual_level ?? 0) < (t.actual_level ?? 0))
      lines.push(`On ${name}, ${otherName} is at level ${o.actual_level} and ${topName} at level ${t.actual_level}.`);
    else if ((o.confidence ?? 0) < (t.confidence ?? 0))
      lines.push(`On ${name}, ${topName}'s proof is backed by more kinds of evidence (${pct(t.confidence, 0)} sure against ${pct(o.confidence, 0)}).`);
    else if ((o.freshness ?? 0) < (t.freshness ?? 0))
      lines.push(`On ${name}, ${otherName}'s proof is older: ${pct(o.freshness, 0)} fresh against ${pct(t.freshness, 0)} for ${topName}.`);
    else lines.push(`On ${name}, ${topName} has more recent work on record.`);
  }
  if (!lines.length) lines.push(`${otherName} and ${topName} are level on every skill the engine measured; the small gap comes from volume of evidence.`);
  return lines;
}

export function exclusionExplain(e: ExcludedCandidate, critical: string[] | undefined, minCoverage: number | null | undefined, nameOf: NameOf): string {
  if (e.reason === "missing_critical_skill") {
    const list = (critical ?? []).map(nameOf).join(", ") || "a skill this role cannot do without";
    return `No proof of ${list}. The role cannot be filled without it, so they are not shortlisted however strong they are elsewhere.`;
  }
  if (e.reason === "below_min_coverage")
    return `Proof exists for too few of the required skills. The role needs evidence for at least ${minCoverage ? pct(minCoverage, 0) : "a set share"} of them.`;
  if (e.reason === "no_evidence_on_any_required_skill") return "Nothing is on file for any of the skills this role needs.";
  return e.reason;
}

export const GLOSSARY: { term: string; text: string }[] = [
  { term: "Fit", text: "A comparison between the people considered for this role. It is not a pass mark. It stays low for everyone when little proof of work is on file, so read it as 'who is ahead', not 'who is good enough'." },
  { term: "Level (L1 to L5)", text: "How capable the proof shows someone to be: 1 Awareness, 2 Working, 3 Proficient, 4 Advanced, 5 Expert. A role says the level it needs; the person's level comes from their evidence." },
  { term: "Confidence", text: "How sure Hermes is. It rises when different kinds of proof agree: tickets alone are 35%, tickets plus a certificate about 90%." },
  { term: "Freshness", text: "How recent the proof is. Skills fade over time, fast ones such as containers in months, slow ones in years, so old proof counts for less." },
  { term: "Volume", text: "How much real work backs the skill. More tickets mean a more dependable level." },
  { term: "Kinds of proof", text: "Tickets (real work, counts most), certificates, and claims a manager has confirmed (counts least). Unconfirmed self-claims are ignored." },
  { term: "Related skill credit", text: "Some skills are close cousins. If someone lacks one but has its cousin, they get partial credit, clearly labelled." },
  { term: "Critical skill", text: "A skill the role cannot do without. Anyone with no proof of it is not shortlisted, whatever else they know." },
];
