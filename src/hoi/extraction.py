"""Requirement extraction: deterministic rules first, optional LLM assist, always verified and advisory.

Every extracted value carries ``source`` (document id, character span, verbatim quote) and a heuristic
``confidence`` (rule-based, NOT calibrated — see docs/HOI_TEST_PLAN.md). Anything the document does not
state stays ``None``/unknown. Values whose quote cannot be found verbatim in the source are rejected.
Output is a DRAFT; nothing is usable for matching until a human approves it.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from phase8.aliases import ontology_lookup_map
from phase8.workbook import normalize_label
from shared.taxonomy import SkillsTaxonomy, load_taxonomy

PARSER_VERSION = "hoi-rules-1.0"
MAX_ROLES = 50          # matches the edit API (RoleIn list limit); a draft must always be editable and approvable
MAX_SKILLS_PER_ROLE = 60

_HEADER_ROLE = re.compile(r"^\s*(?:Role|Position|Resource|Job Title)\s*[:\-]\s*(?P<title>\S.{1,100}?)\s*$", re.I)
_HEADER_NX = re.compile(r"^\s*(?:\d+[.)]\s*)?(?P<n>\d{1,3})\s*[x×]\s+(?P<title>[A-Za-z][^\n]{2,90}?)\s*$")
_HEADCOUNT = re.compile(r"^\s*(?:Headcount|Positions?|Openings?|Number of (?:resources|positions))\s*[:\-]\s*(?P<v>\d{1,3})\b", re.I)
_FTE = re.compile(r"^\s*(?:FTE|Allocation)\s*[:\-]\s*(?P<v>\d*\.?\d+)\s*$", re.I)
_LOCATION = re.compile(r"^\s*Location\s*[:\-]\s*(?P<v>\S.{0,100}?)\s*$", re.I)
_START = re.compile(r"^\s*Start(?:\s+date)?\s*[:\-]\s*(?P<v>\d{4}-\d{2}-\d{2})\b", re.I)
_END = re.compile(r"^\s*End(?:\s+date)?\s*[:\-]\s*(?P<v>\d{4}-\d{2}-\d{2})\b", re.I)
_YEARS = re.compile(r"\b(?P<v>\d{1,2})\s*\+?\s*(?:years?|yrs?)\b", re.I)
_SKILL_LINE = re.compile(r"^\s*(?P<kind>Must[- ]have(?: skills)?|Required skills?|Mandatory skills?|Preferred skills?|Nice[- ]to[- ]have(?: skills)?)\s*[:\-]\s*(?P<v>\S.*)$", re.I)
_CERT_LINE = re.compile(r"^\s*(?P<kind>Required |Mandatory |Preferred |Desired )?Certifications?\s*[:\-]\s*(?P<v>\S.*)$", re.I)
_LEVEL = re.compile(r"\(?\b(?:level|lvl|L)\s*([1-5])\b\)?|\(\s*([1-5])\s*/\s*5\s*\)", re.I)


def _valid_date(s: str) -> bool:
    try:
        date.fromisoformat(s)
        return True
    except ValueError:
        return False


def _lines(text: str) -> List[Tuple[int, int, str]]:
    out, pos = [], 0
    for raw in text.split("\n"):
        out.append((pos, pos + len(raw), raw))
        pos += len(raw) + 1
    return out


def _src(doc_id: str, start: int, end: int, text: str) -> Dict[str, Any]:
    return {"document_id": doc_id, "start": start, "end": end, "quote": text[start:end]}


def verify_source(src: Mapping[str, Any], texts: Mapping[str, str]) -> bool:
    t = texts.get(src.get("document_id", ""))
    if t is None:
        return False
    q = src.get("quote") or ""
    s, e = src.get("start"), src.get("end")
    return bool(q) and isinstance(s, int) and isinstance(e, int) and t[s:e] == q


def _field(value: Any, src: Dict[str, Any], conf: float) -> Dict[str, Any]:
    return {"value": value, "source": src, "confidence": conf, "origin": "extracted"}


def _split_items(v: str) -> List[str]:
    return [p.strip(" .") for p in re.split(r"[;,]", v) if p.strip(" .")]


def _skill_item(raw: str, criticality: str, src: Dict[str, Any], lookup: Mapping[str, str]) -> Dict[str, Any]:
    lvl_m = _LEVEL.search(raw)
    level = int(lvl_m.group(1) or lvl_m.group(2)) if lvl_m else None
    label = _LEVEL.sub("", raw).strip(" ()")
    skill_id = lookup.get(normalize_label(label))
    return {
        "text": label, "skill_id": skill_id, "level": level, "criticality": criticality,
        "taxonomy_status": "mapped" if skill_id else "unmapped",
        "source": src, "confidence": 0.9 if skill_id else 0.5, "origin": "extracted", "dismissed": False,
    }


def extract_rules(documents: Sequence[Tuple[str, str]], taxonomy: Optional[SkillsTaxonomy] = None) -> Dict[str, Any]:
    tax = taxonomy or load_taxonomy()
    lookup = ontology_lookup_map(tax)
    roles: List[Dict[str, Any]] = []
    notes: List[str] = []
    for doc_id, text in documents:
        cur: Optional[Dict[str, Any]] = None
        for start, end, line in _lines(text):
            if not line.strip():
                continue
            m = _HEADER_ROLE.match(line) or _HEADER_NX.match(line)
            if m:
                title_start = start + line.index(m.group("title"))
                cur = {"role_name": m.group("title").strip(), "origin": "extracted",
                       "fields": {"role_name": _field(m.group("title").strip(),
                                                      _src(doc_id, title_start, title_start + len(m.group("title")), text), 0.9)},
                       "skills": [], "constraints": {}, "headcount": None, "fte": None, "location": None,
                       "start_date": None, "end_date": None}
                if "n" in m.groupdict() and m.groupdict().get("n"):
                    cur["headcount"] = int(m.group("n"))
                    cur["fields"]["headcount"] = _field(cur["headcount"], _src(doc_id, start, end, text), 0.85)
                roles.append(cur)
                continue
            if cur is None:
                continue
            line_src = _src(doc_id, start, end, text)
            for rx, key, cast in ((_HEADCOUNT, "headcount", int), (_FTE, "fte", str), (_LOCATION, "location", str)):
                mm = rx.match(line)
                if mm:
                    val = cast(mm.group("v"))
                    if key == "fte":
                        try:
                            ok = 0 < float(val) <= 1
                        except ValueError:
                            ok = False
                        if not ok:
                            notes.append(f"rejected_fte:{val}")
                            continue
                    if key == "headcount" and val < 1:
                        continue
                    cur[key] = val
                    cur["fields"][key] = _field(val, line_src, 0.85)
            for rx, key in ((_START, "start_date"), (_END, "end_date")):
                mm = rx.match(line)
                if mm:
                    if _valid_date(mm.group("v")):
                        cur[key] = mm.group("v")
                        cur["fields"][key] = _field(mm.group("v"), line_src, 0.85)
                    else:
                        notes.append(f"rejected_date:{mm.group('v')}")
            ym = _YEARS.search(line)
            if ym and re.search(r"experience|exp\b", line, re.I):
                cur["constraints"]["years_experience_min"] = int(ym.group("v"))
                cur["fields"]["years_experience_min"] = _field(int(ym.group("v")), line_src, 0.75)
            sm = _SKILL_LINE.match(line)
            if sm:
                crit = "preferred" if re.match(r"preferred|nice", sm.group("kind"), re.I) else "must"
                base = start + line.index(sm.group("v"))
                off = 0
                for item in re.split(r"([;,])", sm.group("v")):
                    if item in (";", ","):
                        off += 1
                        continue
                    stripped = item.strip(" .")
                    if stripped:
                        s0 = base + off + item.index(stripped)
                        cur["skills"].append(_skill_item(stripped, crit, _src(doc_id, s0, s0 + len(stripped), text), lookup))
                    off += len(item)
                continue
            cm = _CERT_LINE.match(line)
            if cm:
                kind = (cm.group("kind") or "").strip().lower()
                key = "preferred_certifications" if kind in ("preferred", "desired") else "mandatory_certifications"
                cur["constraints"].setdefault(key, []).extend(_split_items(cm.group("v")))
                cur["fields"][key] = _field(cur["constraints"][key], line_src, 0.85)
    roles = merge_duplicate_roles(roles, notes)
    if len(roles) > MAX_ROLES:
        notes.append(f"truncated_roles:{len(roles)}_found_first_{MAX_ROLES}_kept (document is unusually large; split it)")
        roles = roles[:MAX_ROLES]
    for r in roles:
        if len(r["skills"]) > MAX_SKILLS_PER_ROLE:
            notes.append(f"truncated_skills:{r['role_name']}:{len(r['skills'])}_found_first_{MAX_SKILLS_PER_ROLE}_kept")
            r["skills"] = r["skills"][:MAX_SKILLS_PER_ROLE]
    if not roles:
        notes.append("no_roles_detected")
    return {"roles": roles, "notes": notes, "parser_version": PARSER_VERSION, "method": "rules"}


def _rkey(name: str) -> str:
    return normalize_label(name)


def merge_duplicate_roles(roles: List[Dict[str, Any]], notes: List[str]) -> List[Dict[str, Any]]:
    """One role per normalised name, across and within documents (e.g. SOW + JD, or a re-uploaded file).

    Nothing is silently reconciled: where two sources disagree on a value, the first source's value is kept and a
    ``conflict:`` note names both so a person can resolve it. Missing values are filled from the other source;
    skills are de-duplicated (must-have wins over preferred, higher stated level wins, both with a note).
    """
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for r in roles:
        k = _rkey(r["role_name"])
        if k not in merged:
            merged[k] = r
            order.append(k)
            continue
        base = merged[k]
        notes.append(f"merged_duplicate_role:{base['role_name']}")
        for f in ("headcount", "fte", "location", "start_date", "end_date"):
            a, b = base.get(f), r.get(f)
            if a is None and b is not None:
                base[f] = b
                if f in r.get("fields", {}):
                    base["fields"][f] = r["fields"][f]
            elif a is not None and b is not None and str(a) != str(b):
                notes.append(f"conflict:{base['role_name']}:{f}:{a}!={b} (kept first; reviewer must reconcile)")
        for ck, cv in r.get("constraints", {}).items():
            cur = base["constraints"].get(ck)
            if isinstance(cv, list):
                base["constraints"][ck] = list(dict.fromkeys((cur or []) + cv))
            elif cur is None:
                base["constraints"][ck] = cv
            elif ck == "years_experience_min":
                base["constraints"][ck] = max(cur, cv)
        for fk, fv in r.get("fields", {}).items():
            base["fields"].setdefault(fk, fv)
        seen = {_rkey(sk["text"]): sk for sk in base["skills"]}
        for sk in r["skills"]:
            old = seen.get(_rkey(sk["text"]))
            if old is None:
                base["skills"].append(sk)
                seen[_rkey(sk["text"])] = sk
                continue
            if sk["criticality"] == "must" and old["criticality"] != "must":
                old["criticality"] = "must"
                notes.append(f"skill_promoted_to_must:{old['text']}")
            if sk.get("level") is not None and (old.get("level") is None or sk["level"] > old["level"]):
                if old.get("level") is not None:
                    notes.append(f"conflict:{old['text']}:level:{old['level']}!={sk['level']} (kept higher)")
                old["level"], old["source"] = sk["level"], sk["source"]
    return [merged[k] for k in order]


# ------------------------------------------------------------------ optional LLM assist
LLM_SYSTEM = (
    "You extract staffing requirements from a customer document. Reply with JSON only, matching exactly: "
    '{"roles":[{"role":"","headcount":null,"fte":null,"location":null,"skills":[{"skill":"",'
    '"criticality":"must|preferred","quote":""}]}]}. Use null when the document does not say. '
    "Every skill MUST include a quote copied verbatim from the document. Never guess."
)


def _loads_tolerant(raw: str) -> Dict[str, Any]:
    """Parse the model's JSON. Small local models often emit a stray quote before an object (``,"{"skill"...``); that single
    glitch is repaired deterministically. Anything else still raises, and every value is verified against the document anyway."""
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ValueError("no JSON object in model output")
    body = m.group(0)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(re.sub(r'(?<=[,\[])\s*"\{', "{", body))
    except json.JSONDecodeError:
        return _salvage(body)


_SKILL_TRIPLE = re.compile(r'"skill"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,\s*"criticality"\s*:\s*"(must|preferred)"\s*,\s*"quote"\s*:\s*"((?:[^"\\]|\\.)*)"')
_ROLE_NAME = re.compile(r'"role"\s*:\s*"((?:[^"\\]|\\.)*)"')


def _salvage(body: str) -> Dict[str, Any]:
    """Last resort for malformed JSON: read the fixed-shape skill triples per role. Quotes are still verified against the
    document afterwards, so salvaged content gets no extra trust."""
    marks = list(_ROLE_NAME.finditer(body))
    roles = []
    for i, m in enumerate(marks):
        seg = body[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(body)]
        skills = [{"skill": a, "criticality": b, "quote": c} for a, b, c in _SKILL_TRIPLE.findall(seg)]
        roles.append({"role": m.group(1), "skills": skills})
    if not roles:
        raise ValueError("model output could not be parsed")
    return {"roles": roles}


def merge_llm(base: Dict[str, Any], provider: Any, documents: Sequence[Tuple[str, str]],
              taxonomy: Optional[SkillsTaxonomy] = None) -> Dict[str, Any]:
    """Add only verifiable LLM suggestions. Any failure leaves the rule-based draft untouched."""
    tax = taxonomy or load_taxonomy()
    lookup = ontology_lookup_map(tax)
    texts = dict(documents)
    notes = list(base["notes"])
    roles = base["roles"]
    added = 0
    for doc_id, text in documents:
        try:
            raw = provider.generate(f"Document:\n{text[:12000]}\n\nJSON:", system=LLM_SYSTEM, timeout=60.0)
            data = _loads_tolerant(raw)
        except Exception as exc:  # noqa: BLE001 - assist is optional; never block the draft
            notes.append(f"llm_unavailable:{type(exc).__name__}")
            return {**base, "notes": notes}
        for r in data.get("roles", []) if isinstance(data, dict) else []:
            title = str(r.get("role") or "").strip()
            if not title:
                continue
            target = next((x for x in roles if x["role_name"].lower() == title.lower()), None)
            for sk in r.get("skills", []) or []:
                quote = str(sk.get("quote") or "")
                pos = text.find(quote) if quote else -1
                if pos < 0:
                    notes.append(f"llm_rejected_unverifiable_skill:{str(sk.get('skill'))[:40]}")
                    continue
                if target is None:
                    tpos = text.find(title)
                    if tpos < 0:
                        notes.append(f"llm_rejected_unverifiable_role:{title[:40]}")
                        break
                    target = {"role_name": title, "origin": "llm", "skills": [], "constraints": {}, "headcount": None,
                              "fte": None, "location": None, "start_date": None, "end_date": None,
                              "fields": {"role_name": _field(title, _src(doc_id, tpos, tpos + len(title), text), 0.4)}}
                    roles.append(target)
                label = str(sk.get("skill") or "").strip()
                if not label:
                    continue
                item = _skill_item(label, "preferred" if sk.get("criticality") == "preferred" else "must",
                                   _src(doc_id, pos, pos + len(quote), text), lookup)
                if any(normalize_label(item["text"]) == normalize_label(s["text"]) for s in target["skills"]):
                    continue  # the rules already found it (compared after the "(level N)" suffix is stripped)
                item["origin"], item["confidence"] = "llm", min(item["confidence"], 0.6)
                target["skills"].append(item)
                added += 1
    notes.append(f"llm_suggestions:{added}_new_verified_items")
    return {**base, "roles": roles, "notes": notes, "method": "rules+llm"}


def validate_for_approval(roles: Sequence[Mapping[str, Any]], known_skill_ids: Sequence[str]) -> List[str]:
    """Return blocking problems. Empty list == approvable. Unknown stays unknown: nothing is auto-filled."""
    problems: List[str] = []
    known = set(known_skill_ids)
    if not roles:
        problems.append("no_roles")
    for i, r in enumerate(roles, start=1):
        tag = f"role[{i}]"
        if not str(r.get("role_name") or "").strip():
            problems.append(f"{tag}:role_name_missing")
        hc = r.get("headcount")
        if not isinstance(hc, int) or isinstance(hc, bool) or hc < 1:
            problems.append(f"{tag}:headcount_unknown")
        try:
            f = float(r.get("fte")) if r.get("fte") is not None else None
        except (TypeError, ValueError):
            f = None
        if f is None or not 0 < f <= 1:
            problems.append(f"{tag}:fte_unknown")
        live = [s for s in r.get("skills", []) if not s.get("dismissed")]
        if not any(s.get("criticality") == "must" for s in live):
            problems.append(f"{tag}:no_must_have_skill")
        for s in live:
            lbl = s.get("text") or s.get("skill_id")
            if s.get("skill_id") not in known:
                problems.append(f"{tag}:skill_unmapped:{lbl}")
            elif not isinstance(s.get("level"), int) or isinstance(s.get("level"), bool) or not 1 <= s["level"] <= 5:
                problems.append(f"{tag}:skill_level_unknown:{s['skill_id']}")
    return problems
