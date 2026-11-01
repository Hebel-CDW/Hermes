import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useState } from "react";
import { managerToolsApi, skillsApi } from "../api/endpoints";
import type { BulkItem, SkillSummaryRow, TeamGrid as Grid } from "../api/types";
import { downloadText, matchImport, parsePasted, toCsv, type ImportProblem } from "../lib/csv";
import { useNames } from "../lib/names";
import { useApi, useStale } from "../lib/useApi";
import { PageHead } from "../ui/Bits";
import { Burst, LEVEL_COLOR, useCalm, useToasts } from "../ui/Fx";
import { EmptyState, ErrorState, InlineError, Loading } from "../ui/States";

const key = (coded: string, skill: string) => `${coded}|${skill}`;

export default function TeamGrid() {
  const q = useApi(
    async (s) => {
      const [grid, skills] = await Promise.all([managerToolsApi.grid(s), skillsApi.list(s)]);
      return { grid, skills: skills.skills };
    },
    [],
  );
  const data = useStale(q);
  return (
    <>
      <PageHead
        trail={["Bulk update"]}
        title="Bulk update"
        lede="Edit the whole team like a spreadsheet. Everything you save is recorded as a manager-confirmed skill."
      />
      {q.status === "loading" && !data && <Loading label="Loading your team" rows={4} />}
      {q.status === "error" && <ErrorState error={q.error} onRetry={q.reload} />}
      {data &&
        (data.grid.people.length === 0 ? (
          <EmptyState title="No one on your team">Your principal has no direct reports in this database.</EmptyState>
        ) : (
          <GridBody grid={data.grid} skills={data.skills} reload={q.reload} />
        ))}
    </>
  );
}

function GridBody({ grid, skills, reload }: { grid: Grid; skills: SkillSummaryRow[]; reload: () => void }) {
  const { label, people: directory } = useNames();
  const calm = useCalm();
  const { push, host } = useToasts();
  const nameOf = (s: string) => skills.find((x) => x.skill_id === s)?.name ?? s;

  const topSkills = useMemo(() => {
    const counts = new Map<string, number>();
    for (const cells of Object.values(grid.cells)) for (const s of Object.keys(cells)) counts.set(s, (counts.get(s) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 8).map(([s]) => s);
  }, [grid]);

  const [cols, setCols] = useState<string[]>(topSkills);
  const [edits, setEdits] = useState<Record<string, number>>({});
  const [filter, setFilter] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [fire, setFire] = useState(0);
  const [showImport, setShowImport] = useState(false);
  const [pasted, setPasted] = useState("");
  const [problems, setProblems] = useState<ImportProblem[]>([]);
  const [ready, setReady] = useState<number | null>(null);

  const people = grid.people.filter((p) => !filter.trim() || label(p).toLowerCase().includes(filter.trim().toLowerCase()));
  const changeCount = Object.keys(edits).length;

  const setCell = (coded: string, skill: string, value: number) => {
    const current = grid.cells[coded]?.[skill]?.level ?? 0;
    setEdits((e) => {
      const next = { ...e };
      if (value === 0 || value === current) delete next[key(coded, skill)];
      else next[key(coded, skill)] = value;
      return next;
    });
  };

  const save = async () => {
    setPending(true);
    setError(null);
    const items: BulkItem[] = Object.entries(edits).map(([k, proficiency]) => {
      const [coded_identity, skill_id] = k.split("|");
      return { coded_identity, skill_id, proficiency, note: "bulk update" };
    });
    try {
      let saved = 0;
      for (let i = 0; i < items.length; i += 200) saved += (await managerToolsApi.bulk(items.slice(i, i + 200))).saved;
      push(`Saved ${saved} skill update${saved === 1 ? "" : "s"}`, "ok");
      setFire((n) => n + 1);
      setEdits({});
      setTimeout(reload, 500);
    } catch (e) {
      setError(e as Error);
    } finally {
      setPending(false);
    }
  };

  const checkPaste = () => {
    const { items, problems: bad } = matchImport(
      parsePasted(pasted),
      directory,
      skills.map((s) => ({ skill_id: s.skill_id, name: s.name })),
      new Set(grid.people),
    );
    setProblems(bad);
    setReady(items.length);
    if (items.length) {
      setCols((c) => [...new Set([...c, ...items.map((i) => i.skill_id)])]);
      setEdits((e) => {
        const next = { ...e };
        for (const it of items) {
          if ((grid.cells[it.coded_identity]?.[it.skill_id]?.level ?? 0) !== it.proficiency) next[key(it.coded_identity, it.skill_id)] = it.proficiency;
        }
        return next;
      });
    }
  };

  const exportCsv = () =>
    downloadText(
      "team-skills.csv",
      toCsv([
        ["Person", ...cols.map(nameOf)],
        ...grid.people.map((p) => [label(p), ...cols.map((s) => grid.cells[p]?.[s]?.level ?? "")]),
      ]),
    );

  const addable = skills.filter((s) => !cols.includes(s.skill_id));

  return (
    <>
      <Burst fire={fire} />
      {host}
      <section className="panel">
        <div className="panel-body grid-toolbar">
          <label className="field compact">
            <span className="label">Find a person</span>
            <input className="input" aria-label="Find a person" placeholder="Type a name" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </label>
          <label className="field compact">
            <span className="label">Add a skill column</span>
            <select
              className="select"
              aria-label="Add a skill column"
              value=""
              onChange={(e) => e.target.value && setCols((c) => [...c, e.target.value])}
            >
              <option value="">Choose a skill…</option>
              {addable.map((s) => (
                <option key={s.skill_id} value={s.skill_id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <div className="grid-toolbar-actions">
            <button className="btn btn-sm" onClick={() => setShowImport((v) => !v)} aria-expanded={showImport}>
              Paste from Excel
            </button>
            <button className="btn btn-sm" onClick={exportCsv}>
              Download CSV
            </button>
          </div>
        </div>
        <AnimatePresence initial={false}>
          {showImport && (
            <motion.div
              key="import"
              initial={calm ? false : { height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              style={{ overflow: "hidden" }}
            >
              <div className="panel-body import-box">
                <p className="ink-2" style={{ marginTop: 0 }}>
                  Paste rows from your sheet as <strong>Person, Skill, Level</strong> (tab or comma separated). People and skills must match exactly; anything
                  that does not is listed below and never guessed.
                </p>
                <textarea
                  className="input"
                  aria-label="Pasted rows"
                  rows={5}
                  value={pasted}
                  placeholder={"Jordan Lee\tContainer Orchestration\t4"}
                  onChange={(e) => setPasted(e.target.value)}
                />
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 8 }}>
                  <button className="btn btn-sm btn-primary" disabled={!pasted.trim()} onClick={checkPaste}>
                    Check rows and add to grid
                  </button>
                  {ready !== null && (
                    <span className="ink-2" role="status">
                      {ready} ready · {problems.length} need attention
                    </span>
                  )}
                </div>
                {problems.length > 0 && (
                  <ul className="import-problems">
                    {problems.slice(0, 12).map((p) => (
                      <li key={p.line}>
                        <strong>Row {p.line}:</strong> {p.reason}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </section>

      <div className="grid-wrap">
        <table className="data team-grid" aria-label="Team skills grid">
          <thead>
            <tr>
              <th className="sticky-col">Person</th>
              {cols.map((s) => (
                <th key={s}>
                  <span className="col-head">
                    {nameOf(s)}
                    <button className="icon-btn tiny" aria-label={`Hide ${nameOf(s)}`} onClick={() => setCols((c) => c.filter((x) => x !== s))}>
                      ×
                    </button>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {people.map((p) => (
              <tr key={p}>
                <th className="sticky-col" scope="row">
                  {label(p)}
                </th>
                {cols.map((s) => {
                  const cell = grid.cells[p]?.[s];
                  const edited = edits[key(p, s)];
                  const shown = edited ?? cell?.level ?? 0;
                  return (
                    <td key={s} className={`gcell ${edited ? "edited" : ""}`} style={{ background: LEVEL_COLOR[shown] }}>
                      <select
                        className="gselect"
                        aria-label={`${label(p)} · ${nameOf(s)}`}
                        title={cell ? `Confidence ${Math.round(cell.confidence * 100)}% · freshness ${Math.round(cell.freshness * 100)}%` : "No proof on file"}
                        value={shown}
                        onChange={(e) => setCell(p, s, Number(e.target.value))}
                      >
                        {!cell && <option value={0}>—</option>}
                        {[1, 2, 3, 4, 5].map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint" style={{ marginTop: 10 }}>
        Saved levels are recorded as manager-confirmed claims. Tickets and certificates still count more, so a claim alone never outranks real work.
      </p>
      <InlineError error={error} />

      <AnimatePresence>
        {changeCount > 0 && (
          <motion.div
            className="savebar"
            role="region"
            aria-label="Unsaved changes"
            initial={calm ? false : { y: 80, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 32 }}
          >
            <span>
              <strong>{changeCount}</strong> unsaved change{changeCount === 1 ? "" : "s"}
            </span>
            <button className="btn btn-sm" disabled={pending} onClick={() => setEdits({})}>
              Discard
            </button>
            <button className="btn btn-primary btn-sm" disabled={pending} onClick={save}>
              {pending ? "Saving…" : `Save ${changeCount} change${changeCount === 1 ? "" : "s"}`}
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
