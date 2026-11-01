/** CSV and paste helpers. Presentation and file plumbing only; nothing here scores anything. */

export type Cell = string | number | null | undefined;

const quote = (v: Cell): string => {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export const toCsv = (rows: Cell[][]): string => rows.map((r) => r.map(quote).join(",")).join("\r\n");

/** Saves text as a file in the browser. Safe to call where downloads are unavailable (it just does nothing). */
export function downloadText(filename: string, text: string, mime = "text/csv;charset=utf-8"): void {
  try {
    const url = URL.createObjectURL(new Blob([text], { type: mime }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch {
    /* downloads unavailable (tests, locked-down browsers) */
  }
}

/** Splits pasted spreadsheet text into rows of cells. Tab, comma and semicolon all work; quotes are honoured. */
export function parsePasted(text: string): string[][] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim() !== "");
  return lines.map((line) => {
    const delim = line.includes("\t") ? "\t" : line.includes(";") && !line.includes(",") ? ";" : ",";
    const out: string[] = [];
    let cur = "";
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (inQ) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"';
          i++;
        } else if (ch === '"') inQ = false;
        else cur += ch;
      } else if (ch === '"') inQ = true;
      else if (ch === delim) {
        out.push(cur.trim());
        cur = "";
      } else cur += ch;
    }
    out.push(cur.trim());
    return out;
  });
}

const WORD_LEVEL: Record<string, number> = { awareness: 1, working: 2, proficient: 3, advanced: 4, expert: 5 };

/** "4", "L4", "Level 4", "Expert" -> 4/5. Anything else is null so the row is reported, not guessed. */
export function parseLevel(raw: string): number | null {
  const s = raw.trim().toLowerCase();
  if (WORD_LEVEL[s]) return WORD_LEVEL[s];
  const m = s.match(/^(?:l|lvl|level)?\s*([1-5])(?:\s|$)/);
  return m ? Number(m[1]) : null;
}

export type ImportPerson = { coded_identity: string; display_name: string };
export type ImportSkill = { skill_id: string; name: string };
export type ImportRow = { line: number; coded_identity: string; skill_id: string; proficiency: number };
export type ImportProblem = { line: number; text: string; reason: string };

const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

/**
 * Turns pasted "Person, Skill, Level" rows into updates. Matching is exact on a normalised name or code:
 * an unrecognised person or skill is reported back, never fuzzy-matched. Only people in `allowed` are accepted.
 */
export function matchImport(
  rows: string[][],
  people: ImportPerson[],
  skills: ImportSkill[],
  allowed: Set<string>,
): { items: ImportRow[]; problems: ImportProblem[] } {
  const byPerson = new Map<string, string>();
  for (const p of people) {
    byPerson.set(norm(p.display_name), p.coded_identity);
    byPerson.set(norm(p.coded_identity), p.coded_identity);
  }
  const bySkill = new Map<string, string>();
  for (const s of skills) {
    bySkill.set(norm(s.name), s.skill_id);
    bySkill.set(norm(s.skill_id), s.skill_id);
  }
  const items: ImportRow[] = [];
  const problems: ImportProblem[] = [];
  const seen = new Set<string>();
  rows.forEach((cells, i) => {
    const line = i + 1;
    const text = cells.join(" · ");
    if (i === 0 && /person|name|employee/i.test(cells[0] ?? "") && /skill/i.test(cells[1] ?? "")) return; // header row
    if (cells.length < 3) return void problems.push({ line, text, reason: "Needs three columns: person, skill, level" });
    const coded = byPerson.get(norm(cells[0]));
    if (!coded) return void problems.push({ line, text, reason: `Person "${cells[0]}" was not recognised` });
    if (!allowed.has(coded)) return void problems.push({ line, text, reason: `${cells[0]} is not on your team` });
    const skill = bySkill.get(norm(cells[1]));
    if (!skill) return void problems.push({ line, text, reason: `Skill "${cells[1]}" is not in the governed list` });
    const level = parseLevel(cells[2]);
    if (!level) return void problems.push({ line, text, reason: `Level "${cells[2]}" must be 1 to 5` });
    const key = `${coded}|${skill}`;
    if (seen.has(key)) return void problems.push({ line, text, reason: "Duplicate of an earlier row" });
    seen.add(key);
    items.push({ line, coded_identity: coded, skill_id: skill, proficiency: level });
  });
  return { items, problems };
}
