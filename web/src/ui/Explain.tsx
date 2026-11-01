import type { ReactNode } from "react";
import type { RankedCandidate } from "../api/types";
import { confidenceWords, GLOSSARY, story, type Tone, type Verdict, whyNotAhead } from "../lib/explain";
import { fixed, pct } from "../lib/format";

/** The one-sentence answer, in a coloured callout, before any table. */
export function VerdictBanner({ v }: { v: Verdict }) {
  return (
    <section className={`verdict verdict-${v.tone}`} aria-label="Recommendation" data-testid="verdict">
      <div className="label">Hermes says</div>
      <h2>{v.title}</h2>
      <p>{v.body}</p>
    </section>
  );
}

export function ToneChip({ tone, children, title }: { tone: Tone; children: ReactNode; title?: string }) {
  const cls = tone === "good" ? "chip-ok" : tone === "warn" ? "chip-warn" : tone === "bad" ? "chip-crimson" : "";
  return (
    <span className={`chip ${cls}`} title={title}>
      {children}
    </span>
  );
}

/** Glossary that answers "what does this number mean" without leaving the page. */
export function HowToRead({ open = false }: { open?: boolean }) {
  return (
    <details className="panel section how-to-read" open={open}>
      <summary className="panel-head" style={{ cursor: "pointer" }}>
        <h2>How to read these numbers</h2>
        <span className="muted" style={{ fontSize: 12 }}>
          Plain-English guide
        </span>
      </summary>
      <dl className="panel-body glossary">
        {GLOSSARY.map((g) => (
          <div key={g.term}>
            <dt>{g.term}</dt>
            <dd>{g.text}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

/** Per-person story: what is strong, what falls short, what is missing, how sure we are. */
export function PersonStory({
  c,
  name,
  top,
  topName,
  nameOf,
  defaultOpen,
}: {
  c: RankedCandidate;
  name: string;
  top?: RankedCandidate;
  topName?: string;
  nameOf: (skill: string) => string;
  defaultOpen?: boolean;
}) {
  const s = story(c, nameOf);
  const conf = confidenceWords(s.meanConfidence);
  const matchedSkills = Object.values(c.reasoning_detail).filter((d) => d.status === "matched");
  const singleKind = matchedSkills.filter((d) => (d.confidence ?? 0) < 0.6).length;
  return (
    <details className="story" open={defaultOpen} data-testid="person-story">
      <summary>
        <span className="num">#{c.rank}</span> <strong>{name}</strong>
        <span className="muted"> · fit {pct(c.fitness_score)} · proof for {s.matched} of {s.required} skills</span>
        <ToneChip tone={conf.tone} title={conf.text}>
          {conf.label}
          {s.meanConfidence !== null ? ` · ${pct(s.meanConfidence, 0)}` : ""}
        </ToneChip>
      </summary>
      <div className="story-body">
        {s.covered.length > 0 && <StoryList tone="good" title="Strong where the role needs it" items={s.covered} />}
        {s.short.length > 0 && <StoryList tone="warn" title="Has the skill, below the level needed" items={s.short} />}
        {s.partial.length > 0 && <StoryList tone="neutral" title="Partial credit from a related skill" items={s.partial} />}
        {s.missing.length > 0 && <StoryList tone="bad" title="No proof on file" items={s.missing} />}
        {top && topName && c.rank > 1 && (
          <StoryList tone="neutral" title={`Why not ahead of ${topName}?`} items={whyNotAhead(top, c, topName, name, nameOf)} />
        )}
        <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>
          {matchedSkills.length === 0
            ? "No direct proof on any required skill."
            : singleKind === 0
              ? "Every skill here is backed by more than one kind of proof."
              : `${singleKind} of ${matchedSkills.length} skills rest on one kind of proof only (for example tickets alone); a certificate or manager sign-off would raise how sure we are.`}{" "}
          Fit score {fixed(c.fitness_score, 3)}.
        </p>
      </div>
    </details>
  );
}

function StoryList({ tone, title, items }: { tone: Tone; title: string; items: string[] }) {
  return (
    <div className={`story-list story-${tone}`}>
      <div className="label">{title}</div>
      <ul>
        {items.map((t) => (
          <li key={t}>{t}</li>
        ))}
      </ul>
    </div>
  );
}
