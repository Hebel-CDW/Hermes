"""Grounded Q&A for the Hermes copilot. Advisory only.

The copilot never scores, ranks, writes evidence or decides anything. It receives a plain-text
fact sheet built from what the signed-in principal is already allowed to see, and the language
model may only rephrase and explain those facts. If the model is unavailable the caller gets an
honest offline summary of the same facts rather than an error (Hermes must work with no LLM).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from ai.provider import LLMProvider, LLMUnavailableError
from shared.models import ProficiencyLevel, TargetRoleProfile
from shared.service import HermesService
from shared.taxonomy import load_taxonomy

LEVELS = ["none", "Awareness", "Working", "Proficient", "Advanced", "Expert"]
MAX_QUESTION = 600

SYSTEM_PROMPT = """You are Hermes Copilot, an assistant inside a workforce skills product.
You help a manager choose who should do a piece of work, and help an employee understand and grow their skills.

Rules you must follow:
- Use ONLY the FACTS provided. Never invent people, skills, scores, dates or reasons. If the facts do not contain the answer, say so plainly and point to the page of the app where it can be found.
- Write in simple, short English a non-technical manager would use. No jargon. Answer only what was asked, in at most 4 short sentences, unless asked for more.
- Always say what a number means ("fit 0.53 is well ahead of 0.22") instead of only quoting it.
- Explain WHY, and when asked "why not", explain what is missing or weaker, using the facts.
- Fit is a comparison between people, not a pass mark. Confidence means how many kinds of proof agree (tickets, certificates, manager confirmation). Freshness is how recent the proof is.
- A fit score belongs ONLY to the staffing request it is listed under. Never attach a fit score to a skill, or to a person outside that request.
- Stay on topic. If asked for anything unrelated to people, skills, roles, requests or growth (poems, code, jokes, opinions, pay), reply in ONE sentence that you only help with skills and staffing, and give no other content.
- When the question names a person, a skill or a role, answer from the matching 'FOCUS' lines first.
- Any line marked 'ALREADY WORKED OUT' is the correct answer to that kind of question. Use it as given; never re-derive it from the other lines.
- Copy every number, level and name EXACTLY as written in the FACTS. Do not round, swap or recalculate anything.
- You advise. The person decides. Never claim to have made a decision or changed any data.
"""


def _name_fn(svc: HermesService) -> Callable[[str], str]:
    synthetic = svc.db.get_meta("data_classification") == "synthetic"
    names = {p["coded_identity"]: p["display_name"] for p in svc.db.list_identity_directory()} if synthetic else {}
    return lambda coded: names.get(coded, coded)


def _skill_name_fn() -> Callable[[str], str]:
    names = {s.skill_id: s.name for s in load_taxonomy().all_skills()}
    return lambda sid: names.get(sid, sid.replace("_", " ").title())


def _fresh(f: Optional[float]) -> str:
    if f is None:
        return "no dated proof"
    return "recent" if f >= 0.8 else "fairly recent" if f >= 0.5 else "getting old" if f >= 0.25 else "old"


def _sure(c: Optional[float]) -> str:
    if c is None:
        return "no proof"
    return "very sure" if c >= 0.85 else "fairly sure" if c >= 0.6 else "limited proof (one kind of evidence)"


def _request_lines(stored: Dict[str, Any], who: Callable[[str], str], sk: Callable[[str], str], detail: bool) -> List[str]:
    req = stored.get("requirements") or {}
    needs = ", ".join(
        f"{sk(k)} level {v}{' (critical)' if k in (req.get('critical_skills') or []) else ''}"
        for k, v in (req.get("required_skills") or {}).items()
    )
    result = stored.get("result") or {}
    chosen = stored.get("chosen_coded_identity")
    head = f"Request {stored['request_id']} needs: {needs}. Status: {stored.get('status')}"
    if chosen:
        head += f"; chosen: {who(chosen)} (engine rank {stored.get('engine_rank_of_choice')})"
    lines = [head + "."]
    for c in result.get("candidates", []):
        line = f"  #{c['rank']} {who(c['coded_identity'])}: fit {c['fitness_score']:.3f}"
        calc = c.get("calculation") or {}
        if calc:
            line += f", proof for {calc.get('matched_skill_count')} of {calc.get('required_skill_count')} skills"
        lines.append(line)
        if detail:
            for skill, d in (c.get("reasoning_detail") or {}).items():
                if d.get("status") == "missing":
                    lines.append(f"      {sk(skill)}: NO proof on file (needs level {d.get('required_level')})")
                elif d.get("status") == "adjacent":
                    lines.append(f"      {sk(skill)}: partial credit from related skill {sk(d.get('adjacency_source_skill') or '')}")
                else:
                    lines.append(
                        f"      {sk(skill)}: level {d.get('actual_level')} (needs {d.get('required_level')}), "
                        f"{_sure(d.get('confidence'))}, proof {_fresh(d.get('freshness'))} ({round((d.get('freshness') or 0) * 100)}% fresh), {len(d.get('evidence_ids') or [])} evidence items"
                    )
    cands = result.get("candidates", [])
    if detail and len(cands) > 1:
        top = cands[0]
        for other in cands[1:]:
            diffs = _why_behind(top, other, who, sk)
            lines.append(f"  WHY {who(other['coded_identity'])} IS BEHIND {who(top['coded_identity'])} (ALREADY WORKED OUT): " + " ".join(diffs))
    for e in result.get("excluded_candidates", []):
        lines.append(f"  NOT SHORTLISTED {who(e['coded_identity'])}: {e['reason'].replace('_', ' ')}")
    return lines


def _why_behind(top: Dict[str, Any], other: Dict[str, Any], who: Callable[[str], str], sk: Callable[[str], str]) -> List[str]:
    tn, on = who(top["coded_identity"]), who(other["coded_identity"])
    td, od = top.get("reasoning_detail") or {}, other.get("reasoning_detail") or {}
    rows = []
    for skill in td:
        if skill not in od:
            continue
        t, o = td[skill], od[skill]
        gap = (t.get("contribution") or 0) - (o.get("contribution") or 0)
        if abs(gap) < 0.005:
            continue
        if o.get("status") == "missing":
            msg = f"{on} has no proof of {sk(skill)}; {tn} is at level {t.get('actual_level')}."
        elif t.get("status") == "missing":
            msg = f"{tn} has no proof of {sk(skill)}, but {on} is at level {o.get('actual_level')}."
        elif (o.get("actual_level") or 0) < (t.get("actual_level") or 0):
            msg = f"On {sk(skill)}, {on} is at level {o.get('actual_level')} and {tn} at level {t.get('actual_level')}."
        elif (o.get("confidence") or 0) < (t.get("confidence") or 0):
            msg = f"On {sk(skill)}, {tn}'s proof has more kinds of evidence behind it ({round((t.get('confidence') or 0) * 100)}% sure against {round((o.get('confidence') or 0) * 100)}%)."
        else:
            msg = f"On {sk(skill)}, {on}'s proof is older ({round((o.get('freshness') or 0) * 100)}% fresh against {round((t.get('freshness') or 0) * 100)}% for {tn})."
        rows.append((abs(gap), msg))
    rows.sort(reverse=True)
    return [m for _g, m in rows[:3]] or ["They are level on every measured skill; the small gap comes from the amount of evidence."]



import re

DOMAIN_NOTE = "coverage = share of people who have proof in at least one skill of that area"


def _closeness(svc: HermesService, coded: str, sk: Callable[[str], str]) -> List[Any]:
    """Every role ranked closest-first for one person: (critical_missing, shortfall, gaps, name, met, need, text)."""
    with svc.db.session() as conn:
        roles = conn.execute("SELECT role_id, role_name, required_skills_json, critical_skills_json FROM role_profiles").fetchall()
    scored = []
    for r in roles:
        req = json.loads(r["required_skills_json"])
        role = TargetRoleProfile(role_id=r["role_id"], role_name=r["role_name"], required_skills={k: ProficiencyLevel(v) for k, v in req.items()})
        gaps = svc.gaps(coded, role).gaps
        crit = set(json.loads(r["critical_skills_json"] or "[]"))
        crit_missing = any(g.current_level is None and g.skill_id in crit for g in gaps)
        shortfall = sum(int(g.required_level) - int(g.current_level or 0) for g in gaps) / max(sum(req.values()), 1)
        text = ", ".join(
            f"{sk(g.skill_id)} ({'no proof' if g.current_level is None else 'level ' + str(int(g.current_level))}, needs {int(g.required_level)})" for g in gaps
        )
        scored.append((crit_missing, shortfall, len(gaps), r["role_name"], len(req) - len(gaps), len(req), text))
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return scored


def _mentions(question: str, svc: HermesService, who: Callable[[str], str], sk: Callable[[str], str]):
    q = question.lower()
    people: List[str] = []
    directory = svc.db.list_identity_directory() if svc.db.get_meta("data_classification") == "synthetic" else []
    firsts: Dict[str, List[str]] = {}
    for p in directory:
        full = p["display_name"].lower()
        firsts.setdefault(full.split()[0], []).append(p["coded_identity"])
        if full in q and p["coded_identity"] not in people:
            people.append(p["coded_identity"])
    for first, codes in firsts.items():
        if len(codes) == 1 and re.search(r"\b" + re.escape(first) + r"\b", q) and codes[0] not in people:
            people.append(codes[0])
    for token in re.findall(r"emp-[0-9a-f]{8}", q):
        code = token.upper().replace("EMP-", "EMP-")
        if svc.db.has_coded_identity(code) and code not in people:
            people.append(code)
    skills: List[str] = []
    for s_ in load_taxonomy().all_skills():
        words = [s_.name.lower(), s_.skill_id.replace("_", " ")] + [k.lower() for k in s_.ticket_keywords if len(k) >= 4]
        if any(re.search(r"\b" + re.escape(w) + r"\b", q) for w in words) and s_.skill_id not in skills:
            skills.append(s_.skill_id)
    with svc.db.session() as conn:
        role_rows = conn.execute("SELECT role_id, role_name FROM role_profiles").fetchall()
    roles = [r["role_id"] for r in role_rows if r["role_name"].lower() in q]
    return people[:3], skills[:3], roles[:1]


def _evidence_kinds(svc: HermesService, coded: str) -> Dict[str, set]:
    kinds: Dict[str, set] = {}
    for e in svc.db.evidence_for_identity(coded):
        kinds.setdefault(e["skill_id"], set()).add(e["evidence_type"])
    return kinds


def _person_focus(svc: HermesService, coded: str, who, sk, matrix, by_skill) -> List[str]:
    rows = sorted([m for m in matrix if m.coded_identity == coded], key=lambda m: (-int(m.proficiency), -m.confidence))
    kinds = _evidence_kinds(svc, coded)
    out = [f"FOCUS PERSON {who(coded)} (ALREADY WORKED OUT): has proof for {len(rows)} skills."]
    for m in rows:
        out.append(
            f"    {sk(m.skill_id)}: level {int(m.proficiency)} ({LEVELS[int(m.proficiency)]}), {_sure(m.confidence)} ({round(m.confidence * 100)}%), "
            f"proof {_fresh(m.freshness)} ({round(m.freshness * 100)}% fresh), evidence: {', '.join(sorted(kinds.get(m.skill_id, []))) or 'none'}"
        )
    sole = [sk(m.skill_id) for m in rows if len(by_skill.get(m.skill_id, [])) == 1]
    out.append(
        f"    IF {who(coded)} LEFT (ALREADY WORKED OUT): "
        + (f"these skills would have NO holder left: {', '.join(sole)}." if sole else "no skill would be left without a holder.")
    )
    best = _closeness(svc, coded, sk)[0]
    out.append(f"    Closest role for {who(coded)}: {best[3]} (fully meets {best[4]} of {best[5]}).")
    for c in svc.db.list_open_contests(coded):
        out.append(f"    Open dispute: {sk(c['skill_id']) if c['skill_id'] else 'general'}: \"{c['reason']}\"")
    return out


def _compare(a: str, b: str, who, sk, matrix, needed: Optional[set] = None, critical: Optional[set] = None) -> List[str]:
    ma = {m.skill_id: m for m in matrix if m.coded_identity == a}
    mb = {m.skill_id: m for m in matrix if m.coded_identity == b}
    out = [f"COMPARISON {who(a)} vs {who(b)} (ALREADY WORKED OUT): {who(a)} has {len(ma)} skills, {who(b)} has {len(mb)}."]
    needed = needed or set()
    critical = critical or set()
    ordered = sorted(set(ma) | set(mb), key=lambda x: (x not in needed, sk(x)))
    for skill in ordered:
        x, y = ma.get(skill), mb.get(skill)
        tag = (" [NEEDED by the open request" + (", CRITICAL" if skill in critical else "") + "]") if skill in needed else (" [not needed by the request]" if needed else "")
        if x and y:
            lead = who(a) if (int(x.proficiency), x.confidence, x.freshness) > (int(y.proficiency), y.confidence, y.freshness) else who(b)
            out.append(
                f"    {sk(skill)}{tag}: {who(a)} L{int(x.proficiency)} ({round(x.confidence * 100)}% sure, {round(x.freshness * 100)}% fresh) vs "
                f"{who(b)} L{int(y.proficiency)} ({round(y.confidence * 100)}% sure, {round(y.freshness * 100)}% fresh). Stronger: {lead}."
            )
        elif x:
            out.append(f"    {sk(skill)}{tag}: only {who(a)} has it (L{int(x.proficiency)}).")
        else:
            out.append(f"    {sk(skill)}{tag}: only {who(b)} has it (L{int(y.proficiency)}).")
    return out


def _head_to_head(ctx: Dict[str, Any], a: str, b: str, who, sk) -> List[str]:
    cands = {c["coded_identity"]: c for c in (ctx.get("result") or {}).get("candidates", [])}
    if a not in cands or b not in cands:
        return []
    ca, cb = cands[a], cands[b]
    top, other = (ca, cb) if ca["rank"] < cb["rank"] else (cb, ca)
    gap = top["fitness_score"] - other["fitness_score"]
    rel = gap / top["fitness_score"] if top["fitness_score"] else 0
    verdict = "TOO CLOSE TO CALL: the numbers do not separate them" if rel < 0.05 else "a clear lead" if rel >= 0.45 else "a real but modest lead"
    out = [
        f"HEAD TO HEAD in request {ctx['request_id']} (ALREADY WORKED OUT): {who(top['coded_identity'])} ranks #{top['rank']} with fit {top['fitness_score']:.3f}; "
        f"{who(other['coded_identity'])} ranks #{other['rank']} with fit {other['fitness_score']:.3f}. Difference {gap:.3f}: {verdict}."
    ]
    out += ["    " + line for line in _why_behind(top, other, who, sk)]
    return out


def _skill_focus(skill: str, who, sk, by_skill) -> List[str]:
    rows = sorted(by_skill.get(skill, []), key=lambda m: (-int(m.proficiency), -m.confidence, -m.freshness))
    out = [f"FOCUS SKILL {sk(skill)} (ALREADY WORKED OUT): {len(rows)} holder{'s' if len(rows) != 1 else ''}, best first."]
    for m in rows[:8]:
        out.append(f"    {who(m.coded_identity)}: level {int(m.proficiency)}, {round(m.confidence * 100)}% sure, proof {_fresh(m.freshness)} ({round(m.freshness * 100)}% fresh)")
    return out


def _role_focus(svc: HermesService, role_id: str, matrix, who, sk) -> List[str]:
    with svc.db.session() as conn:
        r = conn.execute("SELECT role_name, required_skills_json, critical_skills_json FROM role_profiles WHERE role_id = ?", (role_id,)).fetchone()
    req = json.loads(r["required_skills_json"])
    crit = set(json.loads(r["critical_skills_json"] or "[]"))
    role = TargetRoleProfile(role_id=role_id, role_name=r["role_name"], required_skills={k: ProficiencyLevel(v) for k, v in req.items()})
    rows = []
    for coded in sorted({m.coded_identity for m in matrix}):
        gaps = svc.gaps(coded, role).gaps
        crit_missing = any(g.current_level is None and g.skill_id in crit for g in gaps)
        shortfall = sum(int(g.required_level) - int(g.current_level or 0) for g in gaps) / max(sum(req.values()), 1)
        text = ", ".join(f"{sk(g.skill_id)} ({'no proof' if g.current_level is None else 'level ' + str(int(g.current_level))}, needs {int(g.required_level)})" for g in gaps)
        rows.append((crit_missing, shortfall, len(gaps), coded, text))
    rows.sort(key=lambda t: (t[0], t[1], t[2]))
    qualified = [who(c) for cm, _s, n, c, _t in rows if n == 0]
    rows = [t for t in rows if t[2] > 0]
    out = [f"FOCUS ROLE {r['role_name']} (ALREADY WORKED OUT): people who ALREADY fully meet it: {', '.join(qualified) if qualified else 'nobody'}."]
    out.append("    People who could GROW into it, least training needed first:")
    for crit_missing, _sf, n, coded, text in rows[:6]:
        out.append(f"    {who(coded)}: " + ("fully meets the role" if n == 0 else f"{n} gap{'s' if n != 1 else ''}: {text}") + (" (no proof of a critical skill)" if crit_missing else ""))
    return out


def _domain_lines(matrix) -> List[str]:
    tax = load_taxonomy()
    people = {m.coded_identity for m in matrix}
    stats = []
    for d in tax.domains:
        ids = {s_.skill_id for s_ in d.skills}
        holders = {m.coded_identity for m in matrix if m.skill_id in ids}
        covered = len({m.skill_id for m in matrix if m.skill_id in ids})
        stats.append((len(holders) / max(len(people), 1), d.name, len(holders), covered, len(ids)))
    stats.sort()
    out = [f"WEAKEST AREA (ALREADY WORKED OUT, {DOMAIN_NOTE}): {stats[0][1]} at {round(stats[0][0] * 100)}% ({stats[0][2]} of {len(people)} people).",
           "AREAS from weakest to strongest coverage:"]
    for share, name, n, covered, total in stats:
        out.append(f"    {name}: {round(share * 100)}% ({n} people), {covered} of {total} skills have at least one holder")
    return out


def manager_facts(svc: HermesService, sub: str, request_id: Optional[str], question: str = "") -> List[str]:
    who, sk = _name_fn(svc), _skill_name_fn()
    matrix = svc.db.load_skills_matrix()
    people = {m.coded_identity for m in matrix}
    out: List[str] = [f"The workforce has {len(people)} people with skill records and {len(matrix)} skill records in total."]
    by_skill: Dict[str, List[Any]] = {}
    for m in matrix:
        by_skill.setdefault(m.skill_id, []).append(m)
    focus: List[str] = []
    if question:
        mp, ms, mr = _mentions(question, svc, who, sk)
        for coded in mp:
            focus += _person_focus(svc, coded, who, sk, matrix, by_skill)
        if len(mp) >= 2:
            ctx = svc.db.get_staffing_request(request_id) if request_id else None
            if ctx is None:
                recent = svc.db.list_staffing_requests(sub)[:1]
                ctx = recent[0] if recent else None
            req_ctx = (ctx or {}).get("requirements") or {}
            if ctx:
                focus += _head_to_head(ctx, mp[0], mp[1], who, sk)
            focus += _compare(mp[0], mp[1], who, sk, matrix, set((req_ctx.get("required_skills") or {}).keys()), set(req_ctx.get("critical_skills") or []))
        for skill in ms:
            focus += _skill_focus(skill, who, sk, by_skill)
        for rid in mr:
            focus += _role_focus(svc, rid, matrix, who, sk)
        if re.search(r"weak|gap|cover|lack|thin|strongest", question.lower()):
            focus += _domain_lines(matrix)
    FOCUS_AT_END = focus
    ones = [f"{sk(sid)} ({who(rows[0].coded_identity)})" for sid, rows in sorted(by_skill.items(), key=lambda kv: sk(kv[0])) if len(rows) == 1]
    all_ids = {sk_.skill_id for sk_ in load_taxonomy().all_skills()}
    nobody_list = sorted(sk(x) for x in all_ids - set(by_skill))
    out.append("SKILLS WITH EXACTLY ONE HOLDER, so a single point of failure (ALREADY WORKED OUT): " + ("; ".join(ones) if ones else "none") + ".")
    out.append(
        "SKILLS NOBODY HAS PROOF OF (ALREADY WORKED OUT): "
        + (", ".join(nobody_list) + "." if nobody_list else f"there are none. Every one of the {len(all_ids)} skills has at least one person with proof, so no skill has zero holders.")
    )
    out.append("Skills coverage (holders = people with proof):")
    for sid in sorted(by_skill, key=lambda s: -len(by_skill[s])):
        rows = by_skill[sid]
        out.append(f"  {sk(sid)}: {len(rows)} holder{'s' if len(rows) != 1 else ''}, best level {max(int(r.proficiency) for r in rows)}")
    all_skills = {s.skill_id for s in load_taxonomy().all_skills()}
    nobody = sorted(sk(s) for s in all_skills - set(by_skill))
    if nobody:
        out.append("Skills nobody has proof of: " + ", ".join(nobody) + ".")
    out.append("People and their strongest skills:")
    per_person: Dict[str, List[Any]] = {}
    for m in matrix:
        per_person.setdefault(m.coded_identity, []).append(m)
    for coded, rows in sorted(per_person.items(), key=lambda kv: who(kv[0])):
        top = sorted(rows, key=lambda r: (-int(r.proficiency), -r.confidence))[:4]
        out.append(
            f"  {who(coded)}: "
            + "; ".join(f"{sk(r.skill_id)} L{int(r.proficiency)} ({_sure(r.confidence)}, {_fresh(r.freshness)})" for r in top)
        )
    with svc.db.session() as conn:
        roles = conn.execute("SELECT role_name, required_skills_json, critical_skills_json FROM role_profiles").fetchall()
    if roles:
        out.append("Role templates available:")
        for r in roles:
            req = json.loads(r["required_skills_json"])
            crit = json.loads(r["critical_skills_json"] or "[]")
            out.append("  " + r["role_name"] + ": " + ", ".join(f"{sk(k)} L{v}{' (critical)' if k in crit else ''}" for k, v in req.items()))
    contests: List[Dict[str, Any]] = []
    for coded in people:
        contests.extend(svc.db.list_open_contests(coded))
    if contests:
        out.append("Open evidence disputes waiting for the manager:")
        for c in contests:
            out.append(f"  {who(c['coded_identity'])} disputes {sk(c['skill_id']) if c['skill_id'] else 'a general item'}: \"{c['reason']}\"")
    wants_request = (not focus) or bool(
        re.search(r"pick|choose|shortlist|request|candidate|\bfit\b|rank|decid|recommend|who should|hire|select", question.lower())
    )
    requests = svc.db.list_staffing_requests(sub)[:6] if wants_request else []
    if requests:
        out.append("The manager's recent staffing requests (most recent first):")
        for i, r in enumerate(requests):
            out.extend(_request_lines(r, who, sk, detail=(r["request_id"] == request_id) or i == 0))
    return out + FOCUS_AT_END


def employee_facts(svc: HermesService, coded: str) -> List[str]:
    sk = _skill_name_fn()
    me = svc.me(coded)
    out = [f"You have proof for {len(me['skills'])} skills, backed by {len(me['evidence'])} pieces of evidence."]
    single = [sk(s["skill_id"]) for s in me["skills"] if s["confidence"] < 0.6]
    multi = [sk(s["skill_id"]) for s in me["skills"] if s["confidence"] >= 0.6]
    out.append(
        "CONFIDENCE (already worked out): "
        + (f"{len(single)} skills rest on only one kind of evidence ({', '.join(single)}), which is why confidence is low there. " if single else "")
        + (f"Skills backed by more than one kind of evidence: {', '.join(multi)}. " if multi else "")
        + "Confidence goes up when a certificate or manager confirmation agrees with the tickets."
    )
    for s in sorted(me["skills"], key=lambda s: -s["proficiency"]):
        kinds = sorted({e["evidence_type"] for e in me["evidence"] if e["skill_id"] == s["skill_id"]})
        out.append(
            f"  {sk(s['skill_id'])}: level {s['proficiency']} ({LEVELS[s['proficiency']]}), {_sure(s['confidence'])}, "
            f"proof {_fresh(s['freshness'])}, evidence kinds: {', '.join(kinds) or 'none'}"
        )
    with svc.db.session() as conn:
        roles = conn.execute("SELECT role_id, role_name, required_skills_json, critical_skills_json FROM role_profiles").fetchall()
    if roles:
        scored = []
        for r in roles:
            req = json.loads(r["required_skills_json"])
            role = TargetRoleProfile(
                role_id=r["role_id"], role_name=r["role_name"], required_skills={k: ProficiencyLevel(v) for k, v in req.items()}
            )
            gaps = svc.gaps(coded, role).gaps
            line = f"{r['role_name']}: you fully meet {len(req) - len(gaps)} of {len(req)} requirements"
            if gaps:
                line += ". Gaps: " + "; ".join(
                    f"{sk(g.skill_id)} (you: {'no proof' if g.current_level is None else 'level ' + str(int(g.current_level))}, the role needs level {int(g.required_level)})"
                    for g in gaps
                )
            crit = set(json.loads(r["critical_skills_json"] or "[]"))
            crit_missing = any(g.current_level is None and g.skill_id in crit for g in gaps)
            shortfall = sum(int(g.required_level) - int(g.current_level or 0) for g in gaps) / max(sum(req.values()), 1)
            scored.append((crit_missing, shortfall, len(gaps), r["role_name"], len(req) - len(gaps), len(req), line))
        scored.sort(key=lambda t: (t[0], t[1], t[2]))
        best = scored[0]
        out.insert(
            1,
            f"YOUR CLOSEST ROLE (already worked out, state it as the answer): {best[3]}. You fully meet {best[4]} of {best[5]} of its requirements"
            + (" and have no proof of one of its critical skills." if best[0] else "."),
        )
        if ". Gaps: " in best[6]:
            # The model confuses one role's required level with another's when every role's gaps are listed,
            # so the closest role's gaps are stated once, on their own, ready to be copied.
            out.insert(
                2,
                f"WHAT IS MISSING FOR {best[3]} (already worked out, state exactly this and nothing else about levels): "
                + best[6].split(". Gaps: ", 1)[1]
                + ".",
            )
        out.append("All roles ranked from CLOSEST to FURTHEST for you:")
        for i, t in enumerate(scored, 1):
            out.append(f"  {i}. {t[6]}")
    for c in me.get("contests", []):
        out.append(
            f"DISPUTE (already worked out): you have an open dispute about {sk(c['skill_id']) if c['skill_id'] else 'your record'}; "
            "it is waiting for your manager, who can confirm or dismiss it. It does not change any ranking until they decide."
        )
    return out


def offline_answer(facts: List[str], role: str) -> str:
    head = "The AI model is not reachable right now, so here is what Hermes can tell you directly from your data."
    keep = [f for f in facts if not f.startswith("  ")][:6]
    if role == "manager":
        recent = [f for f in facts if f.startswith("Request ") or f.startswith("  #") or f.startswith("  NOT SHORTLISTED")][:8]
        return head + "\n" + "\n".join(keep + recent)
    gaps = [f for f in facts if "Gaps:" in f][:4]
    return head + "\n" + "\n".join(keep + gaps)


def ask(provider: Optional[LLMProvider], facts: List[str], question: str, role: str, timeout: float = 90.0) -> Dict[str, Any]:
    question = question.strip()[:MAX_QUESTION]
    prompt = (
        "FACTS (the only information you may use):\n" + "\n".join(facts) + f"\n\nQUESTION from the {role}: {question}\n\n"
        "Answer from the FOCUS, HEAD TO HEAD and 'ALREADY WORKED OUT' lines that match this question, in plain English. "
        "If a HEAD TO HEAD line exists, state who ranks first, the difference, and whether it is too close to call, then the engine's reasons.\n\nAnswer:"
    )
    if provider is None:
        return {"source": "offline", "answer": offline_answer(facts, role)}
    try:
        text = provider.generate(prompt, system=SYSTEM_PROMPT, timeout=timeout).strip()
    except LLMUnavailableError:
        return {"source": "offline", "answer": offline_answer(facts, role)}
    return {"source": "model", "answer": text or offline_answer(facts, role)}
