# PROJECT BIBLE — Hermes

**Document type:** Master context pack (C-suite → CTO → VP Eng → DevOps → IC → LLM handoff)  
**Classification:** Internal, Confidential  
**Initiative:** Project EVOLVE / Project Hermes  
**Runtime posture:** Local-first MVP (Azure/Power Platform stubs retained for a future tenancy)  
**Repo root:** `/Users/hebel/Hermes`  
**Version of this bible:** 1.0 (aligned to codebase as of implementation)  

> **How to use this document**  
> Give this file to a human leader *or* to GPT/Claude/Cursor. It is designed so a model that has *only* this document (plus the repo files it points to) can correctly reason about product intent, architecture, APIs, data model, algorithms, ops, and risks.  
> When implementing changes: treat the **source files listed under “Canonical code”** as ground truth; this bible summarizes and quotes them.

---

## 0. One-paragraph elevator

**Hermes** is a **recommendation-only** skills and workforce intelligence system. It converts operational evidence (resolved tickets, certifications, manager-confirmed declared skills) into a living **coded skills matrix**, then answers two questions: (1) *Who fits this work?* (2) *What should this person learn next?* Managers always approve staffing; Hermes never auto-assigns. Scoring never sees real names or protected demographics—only coded tokens like `EMP-0142`—until an audited shortlist resolution step.

---

## 1. Audience map (what each role needs)

| Role | Care about | Read sections |
|------|------------|---------------|
| **C-suite / VP** | Why it exists, risk, ROI narrative, what is / is not automated | 0, 2, 3, 11, 13 |
| **CTO / Architect** | Hybrid philosophy, fairness-by-architecture, layer boundaries | 2–6, 10, 12 |
| **Product / Delivery** | Screens, worked examples, success metrics | 3, 7, 8, 11 |
| **Engineering IC** | Packages, algorithms, APIs, tests | 5–10, 14 |
| **DevOps / Platform** | Run locally, CI, env vars, SQLite, future Azure | 9, 12, 15 |
| **Security / HR / Fairness** | Guardrails, audits, what data is forbidden | 4, 6, 11 |
| **Any LLM** | Full context pack — read entire bible, then open listed files | All |

---

## 2. Problem, vision, positioning

### Problem
Staffing is done from memory (“who did something like this last time?”). Expertise outside a manager’s network stays invisible. Skill surveys go stale.

### Vision
Make demonstrated capability **visible, searchable, current, and auditable**—with the same discipline applied to infrastructure inventory.

### Positioning pillars
1. **Evidence-first** — demonstrated > certified > declared (weighted, not exclusive).
2. **Coded identity by design** — no names inside scoring.
3. **Fairness by architecture** — schema has no field for protected attributes.
4. **Living inventory** — matrix updates from new evidence, not annual surveys.

### Explicit non-goals (out of scope for MVP)
- Automated staffing assignment  
- Performance review, compensation, or promotion decisions  
- Ingesting any protected demographic attribute  
- Displaying real names inside the core matrix / scoring / Matrix UI  
- Org-wide rollout beyond the coded pilot population  

### Governing slogan
**Rules decide. Rules compute.** Language models / UI / Copilot (future) may only **narrate** engine output—never invent candidates or scores.

---

## 3. Product surfaces (what a user experiences)

### 3.1 Animated operator console (`web/`)
Stack: Vite + React + TypeScript + Framer Motion.

| Route | Job | Notes |
|-------|-----|-------|
| `/` Entry | Brand-first hero: **HERMES** + one line + CTA | Letter stagger + atmosphere drift |
| `/staff` | Pick skill + level → ranked shortlist → optional Resolve names | NarrateBanner: manager approval required |
| `/learn` | Pick coded identity + target role → demand-ranked gaps | No names on this surface |
| `/matrix` | Coverage ring, freshness bars, skill heatmap | **Coded IDs only** |

Visual direction: deep graphite, teal + amber accents; fonts Syne (display) + IBM Plex Sans (body).

### 3.2 FastAPI (`api/main.py`)
HTTP API for judgment + dashboard; serves `web/dist` when built. Dev UI proxies `/api` → `:8000`.

### 3.3 CLI
- `python -m scripts.hermes_query staff ...`  
- `python -m scripts.hermes_query gaps ...`  
- `python -m scripts.dashboard_export` → static HTML report  

### 3.4 Ingestion
`python -m scripts.ingest_fixtures` loads pilot JSON → identity gate → inference → SQLite.

---

## 4. Guardrails (non-negotiable)

1. **Single identity abstraction entry** — all records enter via `IdentityAbstractionGate` / `HermesService.abstract`.  
2. **No protected attributes** — blocked at gate; schema audited (`scripts/fairness_audit.py`). Forbidden fields include age, gender, ethnicity, race, religion, disability, etc. (`PROTECTED_ATTRIBUTE_FIELDS` in `src/shared/models.py`).  
3. **Governed identity resolution** — names only for shortlisted candidates, only for the requesting manager, integrity-chained audit.  
4. **Human override** — every staffing suggestion requires manager approval.  
5. **Full audit lineage** — ingestion, inference, ranking, resolution events in `audit_ledger`.  
6. **Confidence + freshness** on every skill record.  
7. **Leakage audit** — matrix scanned for PII field names, emails, blocklisted display names (`scripts/leakage_audit.py`).

---

## 5. System architecture

```text
[pilot_population.json fixtures]
            |
            v
   scripts/ingest_fixtures.py
            |
            v
   IdentityAbstractionGate  -----> identity_map + identity_vault (names ONLY here)
            |
            v
   SkillInferenceEngine ---------> evidence_staging + skills_matrix
            |
            +---- demand_signals, role_profiles
            |
   +--------+--------+
   |                 |
 Staff/Learn UI   FitnessGapEngine
   FastAPI/CLI           |
                         v
              ranked shortlist / gaps
                         |
              IdentityResolutionGateway  (optional, audited)
                         |
                    display names
```

### Hybrid philosophy (original EVOLVE design)
- **Low-code / orchestration** (future Azure): move data reliably.  
- **Custom Python**: identity, inference, fitness/gap, resolution — must be deterministic and testable.  

**Today (local-first):** fixtures + CLI replace Power Automate; React console replaces Copilot/Power BI runtime; SQLite replaces Azure SQL. Stubs remain under `infra/`, `power-platform/`, `functions/`.

---

## 6. Data model (SQLite) — full schema

Canonical file: [`infra/sqlite/001_schema.sql`](infra/sqlite/001_schema.sql)  
Runtime DB path: `HERMES_DB_PATH` or default `data/hermes.db`

```sql
-- identity_map: coded token <-> irreversible source_hash (SHA-256 of employee key)
-- identity_vault: RESTRICTED — display_name + source_employee_key; NEVER join into matrix UI queries
-- evidence_staging: demonstrated | certified | declared rows
-- skills_matrix: scored skill per coded_identity (confidence, freshness, evidence_ids_json)
-- role_profiles: target roles + required_skills_json
-- demand_signals: skill_id -> demand_weight (0..1) for gap ranking
-- availability: coded_identity -> is_available
-- audit_ledger: integrity-chained events
-- staffing_requests: request_id, requester_id, shortlist_json (for resolve authz)
```

**Timestamps:** ISO-8601 UTC strings (`strftime('%Y-%m-%dT%H:%M:%fZ','now')` or Python `.isoformat()`).

**Pilot fixture shape** (`data/fixtures/pilot_population.json`):
- `pilot_population[]`: `{employee_id, display_name}`  
- `tickets[]`: `{employee_id, ticket_number, short_description, resolved_at}`  
- `certifications[]`: `{employee_id, cert_code, earned_at, skill_id, proficiency}`  
- `declared[]`: `{employee_id, skill_id, proficiency, manager_confirmed, declared_at}`  
- `demand_weights`, `role_senior_cloud`

Synthetic pilot people: E1001 Alex Rivera, E1002 Jordan Lee, E1003 Sam Patel, E1004 Casey Nguyen, E1005 Riley Brooks.

---

## 7. Skills taxonomy

Canonical file: [`taxonomy/skills_ontology.yaml`](taxonomy/skills_ontology.yaml)

Domains (MVP):
- **cloud_platform:** `container_orchestration`, `azure_networking`, `azure_compute`  
- **platform_ops:** `incident_management`, `infrastructure_as_code`  

Each skill has **5 proficiency levels** (1 Awareness … 5 Expert) with written behavioural definitions, ticket keywords, and optional cert codes (e.g. CKA, AZ-700).

Loader: `shared.taxonomy.load_taxonomy()` / `validate_taxonomy_completeness()`.

---

## 8. Worked examples (must remain reproducible)

### A) Staff a Kubernetes migration
1. Manager asks for `container_orchestration` level ≥ 3.  
2. Engine ranks coded candidates; E1001’s token typically ranks first (multiple k8s tickets + CKA + declared).  
3. Resolve shortlist → “Alex Rivera” appears only after audited resolution.  

Tests: `tests/integration/test_pipeline.py`, `tests/e2e/test_local_pipeline.py`, UI `/staff`.

### B) Learning path toward Senior Cloud Engineer
1. Engineer coded as E1003’s token asks gaps vs `senior_cloud_engineer`.  
2. Gaps ranked by `demand_impact` (deficit × demand_weight)—networking / orchestration usually dominate.  

UI: `/learn`.

---

## 9. Runbook (DevOps / local)

### Prerequisites
- Python ≥ 3.9  
- Node 20+ (for `web/`)  
- macOS/Linux shell  

### Bootstrap
```bash
cd /Users/hebel/Hermes
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m scripts.ingest_fixtures
pytest
```

### API
```bash
uvicorn api.main:app --reload --port 8000
# health: GET http://127.0.0.1:8000/health
```

### Web UI (dev)
```bash
cd web
npm install
npm run start:web   # Vite on :5173, proxies /api → :8000
```

### Web UI (served by API)
```bash
cd web && npm run build
uvicorn api.main:app --port 8000
# open http://127.0.0.1:8000/
```

### Environment variables
| Var | Purpose | Default |
|-----|---------|---------|
| `HERMES_DB_PATH` | SQLite file | `data/hermes.db` |
| `IDENTITY_MAP_SECRET` | HMAC salt for tokenization | `local-dev-secret` |
| `HERMES_API_KEY` / `FUNCTION_AUTH_KEY` | Optional API auth header `x-api-key` | empty = open local |
| `SCORING_CONFIG_VERSION` | Version stamp on skill records | `1.0.0` |
| `VITE_HERMES_API_KEY` | Frontend API key if backend requires it | unset |

### CI (`.github/workflows/ci.yml`)
1. pip install  
2. ingest fixtures  
3. pytest (≥80% coverage on custom packages)  
4. leakage + fairness audits  
5. coverage report + CLI smoke  
6. `npm ci` + `npm run build` in `web/`  

### Audits
```bash
python -m scripts.leakage_audit
python -m scripts.fairness_audit
python -m scripts.coverage_report   # expects ≥80% demonstrated coverage on pilot
```

---

## 10. Canonical code map (every important module)

### Judgment engines (`src/`)
| Path | Responsibility |
|------|----------------|
| `src/identity_abstraction/gate.py` | Tokenize employee keys → `EMP-####`; strip PII; reject protected attrs; leakage scanner |
| `src/skill_inference/engine.py` | Ticket keyword → skills; merge evidence; confidence & freshness |
| `src/fitness_gap/engine.py` | Fitness ranking + demand-ranked gaps |
| `src/identity_resolution/gateway.py` | Shortlist + requester-gated name resolution |
| `src/shared/models.py` | Pydantic domain models + forbidden field sets |
| `src/shared/config.py` | Scoring weights |
| `src/shared/taxonomy.py` | YAML ontology loader |
| `src/shared/db.py` | SQLite access layer |
| `src/shared/audit.py` | In-memory + SQLite audit ledger |
| `src/shared/service.py` | Application service wiring engines ↔ DB |

### API / scripts / web
| Path | Responsibility |
|------|----------------|
| `api/main.py` | FastAPI routes + CORS + SPA static |
| `scripts/ingest_fixtures.py` | Fixture → matrix pipeline |
| `scripts/hermes_query.py` | CLI staff/gaps |
| `scripts/narrate.py` | Narrate-only formatter + grounding asserts |
| `scripts/dashboard_export.py` | Static coded-only HTML/JSON |
| `web/src/pages/*` | Entry, Staff, Learn, Matrix |
| `web/src/api/client.ts` | Typed fetch client |
| `web/src/components/*` | Motion UI building blocks |

### Future Azure stubs (not required to run MVP)
`infra/main.bicep`, `infra/sql/001_schema.sql`, `power-platform/**`, `functions/function_app.py` — see `docs/future-azure.md`.

---

## 11. Algorithms (precise enough to reimplement)

### 11.1 Identity abstraction
- Input: raw record with `employee_id` (+ optional `name`/`display_name`).  
- Reject if any key ∈ `PROTECTED_ATTRIBUTE_FIELDS`.  
- Token = `EMP-` + deterministic HMAC-SHA256-derived 4-digit code (collision walk).  
- Strip `IDENTITY_PII_FIELDS` before matrix write.  
- Store display name **only** in `identity_vault` / gate `_display_names`.  

### 11.2 Skill inference / merge
Weights (default): demonstrated **0.55**, certified **0.30**, declared **0.15**.  
Freshness: `0.5 ** (days_since / half_life)` with half_life **180** days.  
Declared without `manager_confirmed` is skipped.  
Proficiency: freshness-weighted vote by level; if demonstrated within ±1 of winner, take max.  
Confidence: sum(contributions) / sum(type weights), floored at `min_confidence` (0.1).  
Freshness on skill record: mean of per-evidence freshness.

### 11.3 Fitness ranking
For each coded identity with evidence on at least one required skill:
```
contrib(skill) = min(1, current_level/required_level) * confidence * freshness
fitness = mean(contrib over required skills) + availability_bonus(if available)
```
Exclude candidates with **no** evidenced match. Sort by fitness desc, take shortlist_size. Every candidate must carry `evidence_ids` + `per_skill_reasoning`.

### 11.4 Gap computation
For each required skill where current < required:
```
demand_impact = demand_weight[skill] * (required - current_or_0)
```
Sort gaps by demand_impact desc.

### 11.5 Resolution
Require `requester_id == staffing_requests.requester_id` and coded id ∈ shortlist. Log `identity_resolution` audit event. Raise `ResolutionDenied` otherwise.

---

## 12. HTTP API contract

Auth: if `HERMES_API_KEY` set, send header `x-api-key: <key>`.

| Method | Path | Body / notes | Response |
|--------|------|--------------|----------|
| GET | `/health` | — | `{status, service, mode}` |
| GET | `/api/skills` | taxonomy | `{skills:[{skill_id,name,description,domain_*}]}` |
| GET | `/api/roles` | SQLite roles | `{roles:[{role_id,role_name,required_skills}]}` |
| GET | `/api/identities` | coded only | `{identities:["EMP-..."]}` |
| GET | `/api/dashboard` | coded matrix stats | coverage, freshness, skill_distribution |
| POST | `/api/identity/abstract` | raw employee record | coded record + stripped_fields |
| POST | `/api/inference/merge` | `{evidence:[EvidenceRecord]}` | `{skills:[SkillRecord]}` |
| POST | `/api/fitness/rank` | `{request_id,requester_id,required_skills,shortlist_size?}` | FitnessResult |
| POST | `/api/fitness/gaps` | `{coded_identity,role_id,role_name,required_skills}` | GapResult |
| POST | `/api/identity/resolve` | `{request_id,requester_id}` | `{resolved:[{coded_identity,display_name,...}]}` |

SPA: if `web/dist` exists, non-API paths serve `index.html`.

---

## 13. Business / risk narrative (C-suite)

**Value:** better-fit staffing; expertise stops being invisible; defensible auditable process; first measured baseline of demonstrated skill coverage (MVP byproduct).

**Risk controls:** no auto-assignment; no protected attributes; names gated; full audit trail; recommendation language only.

**Current limitation:** local-first with synthetic pilot fixtures—not live ServiceNow/LMS/HR. Production connectors are designed but not activated (`docs/runbooks/source-connectors.md`, `docs/future-azure.md`).

**Success metrics (MVP):**
| Metric | Target |
|--------|--------|
| Evidence coverage | ≥ 80% pilot with demonstrated evidence |
| Identity leakage | Zero |
| Ranking traceability | 100% |
| Query latency (engine path) | ≤ 3s |
| Matrix availability | Operational on coded pilot data |

---

## 14. Testing strategy

- **Unit:** gate, inference, fitness/gap, resolution, taxonomy, narrate grounding  
- **Integration:** abstract → infer → rank → resolve  
- **API:** FastAPI TestClient including frontend endpoints  
- **Audits:** leakage + fairness schema  
- **E2E:** ingest → rank → resolve → dashboard HTML has no real names  
- **Coverage gate:** pytest `--cov-fail-under=80` on custom packages  

Run: `pytest` from repo root with venv active.

---

## 15. Dependency stack

**Python:** pydantic, PyYAML, fastapi, uvicorn, httpx (+ pytest, pytest-cov, ruff for dev).  
**Web:** react 18, react-router-dom 6, framer-motion 11, vite 5, typescript 5.  
**Data:** SQLite (stdlib).  

Package config: `pyproject.toml`, `web/package.json`.

---

## 16. Glossary

| Term | Meaning |
|------|---------|
| Coded identity | Anonymised token `EMP-####` used in matrix/scoring |
| Identity Abstraction Gate | Sole deterministic ingress that strips PII |
| Demonstrated / Certified / Declared evidence | Ticket-inferred / cert-backed / manager-confirmed self-report |
| Confidence | Strength of evidence support (0..1) |
| Freshness | Recency decay of evidence (0..1) |
| Fitness & Gap Engine | Deterministic ranker + gap analyzer |
| Identity Resolution Gateway | Logged shortlist-only name reveal |
| Audit ledger | Integrity-chained event history |
| Narrate-only | UI/LLM may only restate engine JSON |

---

## 17. Canonical source excerpts (engines)

### Identity gate — abstract + protect

### Identity Abstraction Gate (full)

Canonical path: `src/identity_abstraction/gate.py`

```python
"""Deterministic identity tokenization and PII stripping."""

from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, MutableMapping, Optional, Set

from shared.models import IDENTITY_PII_FIELDS, PROTECTED_ATTRIBUTE_FIELDS


CODED_ID_PATTERN = re.compile(r"^EMP-\d{4,}$")


@dataclass(frozen=True)
class AbstractionResult:
    coded_identity: str
    record: Dict[str, Any]
    stripped_fields: tuple


class IdentityAbstractionGate:
    """
    Sole ingress for records entering the shared skills matrix.

    Real identifiers are mapped deterministically to EMP-#### tokens using an
    HMAC salt held in Key Vault in production (passed as mapping_secret).
    """

    def __init__(self, mapping_secret: str, existing_map: Optional[Mapping[str, str]] = None) -> None:
        if not mapping_secret:
            raise ValueError("mapping_secret is required")
        self._secret = mapping_secret.encode("utf-8")
        self._forward: Dict[str, str] = dict(existing_map or {})
        self._reverse: Dict[str, str] = {v: k for k, v in self._forward.items()}
        self._display_names: Dict[str, str] = {}

    def tokenize(self, raw_employee_key: str) -> str:
        key = raw_employee_key.strip().lower()
        if key in self._forward:
            return self._forward[key]
        digest = hmac.new(self._secret, key.encode("utf-8"), hashlib.sha256).hexdigest()
        numeric = int(digest[:8], 16) % 10000
        token = f"EMP-{numeric:04d}"
        n = 1
        while token in self._reverse and self._reverse[token] != key:
            numeric = int(digest[n : n + 8], 16) % 10000
            token = f"EMP-{numeric:04d}"
            n += 1
            if n > 24:
                token = f"EMP-{digest[:8].upper()}"
                break
        self._forward[key] = token
        self._reverse[token] = key
        return token

    def resolve_for_gateway(self, coded_identity: str) -> Optional[str]:
        """Used only by Identity Resolution Gateway — not by scoring."""
        if coded_identity not in self._reverse:
            return None
        return self._display_names.get(coded_identity, self._reverse[coded_identity])

    def abstract_record(self, raw: Mapping[str, Any], employee_key_field: str = "employee_id") -> AbstractionResult:
        if employee_key_field not in raw or not raw[employee_key_field]:
            raise ValueError(f"missing employee key field: {employee_key_field}")

        lower_keys = {str(k).lower() for k in raw.keys()}
        blocked = lower_keys & PROTECTED_ATTRIBUTE_FIELDS
        if blocked:
            raise ValueError(f"protected attributes are forbidden: {sorted(blocked)}")

        coded = self.tokenize(str(raw[employee_key_field]))
        cleaned: Dict[str, Any] = {"coded_identity": coded}
        stripped: Set[str] = set()

        for name_field in ("name", "full_name", "display_name"):
            if name_field in raw and raw[name_field]:
                self._display_names[coded] = str(raw[name_field])
                break
        else:
            self._display_names.setdefault(coded, str(raw[employee_key_field]))

        for key, value in raw.items():
            lk = str(key).lower()
            if lk in IDENTITY_PII_FIELDS or lk == employee_key_field.lower():
                stripped.add(key)
                continue
            if lk in PROTECTED_ATTRIBUTE_FIELDS:
                stripped.add(key)
                continue
            cleaned[key] = value

        return AbstractionResult(
            coded_identity=coded,
            record=cleaned,
            stripped_fields=tuple(sorted(stripped)),
        )

    def assert_no_pii(self, record: Mapping[str, Any]) -> None:
        for key in record.keys():
            lk = str(key).lower()
            if lk in IDENTITY_PII_FIELDS:
                raise AssertionError(f"PII field present in coded record: {key}")
            if lk in PROTECTED_ATTRIBUTE_FIELDS:
                raise AssertionError(f"protected attribute present: {key}")
            if isinstance(record[key], str) and "@" in record[key] and "." in record[key]:
                if re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", record[key]):
                    raise AssertionError("email-like value leaked into coded record")

    def export_map(self) -> Dict[str, str]:
        return dict(self._forward)


def scan_for_identity_leakage(
    records: list,
    blocklist: Optional[Set[str]] = None,
) -> list:
    """Return list of leakage findings for automated audit."""
    findings = []
    names = {n.lower() for n in (blocklist or set())}
    for idx, record in enumerate(records):
        if not isinstance(record, (Mapping, MutableMapping)):
            continue
        for key, value in record.items():
            lk = str(key).lower()
            if lk in IDENTITY_PII_FIELDS:
                findings.append({"index": idx, "field": key, "reason": "pii_field"})
            if isinstance(value, str) and value.lower() in names and value.lower():
                findings.append(
                    {"index": idx, "field": key, "reason": "blocklist_hit", "value": value}
                )
            if isinstance(value, str) and re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", value):
                findings.append({"index": idx, "field": key, "reason": "email_pattern"})
        coded = record.get("coded_identity")
        if coded and not CODED_ID_PATTERN.match(str(coded)):
            findings.append({"index": idx, "field": "coded_identity", "reason": "invalid_token"})
    return findings

```

### Skill Inference Engine (full)

Canonical path: `src/skill_inference/engine.py`

```python
"""Convert coded evidence into scored skill records with confidence and freshness."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from shared.config import ScoringConfig, load_scoring_config
from shared.models import (
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    SkillRecord,
)
from shared.taxonomy import SkillsTaxonomy, load_taxonomy


def _days_between(later: datetime, earlier: datetime) -> float:
    if later.tzinfo is None:
        later = later.replace(tzinfo=timezone.utc)
    if earlier.tzinfo is None:
        earlier = earlier.replace(tzinfo=timezone.utc)
    return max(0.0, (later - earlier).total_seconds() / 86400.0)


class SkillInferenceEngine:
    """Deterministic evidence merge and skill scoring."""

    def __init__(
        self,
        taxonomy: Optional[SkillsTaxonomy] = None,
        config: Optional[ScoringConfig] = None,
    ) -> None:
        self.taxonomy = taxonomy or load_taxonomy()
        self.config = config or load_scoring_config()

    def infer_from_ticket(
        self,
        coded_identity: str,
        ticket_text: str,
        occurred_at: datetime,
        source_ref: str,
        evidence_id: str,
    ) -> List[EvidenceRecord]:
        skill_ids = self.taxonomy.match_keywords(ticket_text)
        records: List[EvidenceRecord] = []
        for skill_id in skill_ids:
            records.append(
                EvidenceRecord(
                    evidence_id=f"{evidence_id}:{skill_id}",
                    coded_identity=coded_identity,
                    skill_id=skill_id,
                    evidence_type=EvidenceType.DEMONSTRATED,
                    proficiency=ProficiencyLevel.PROFICIENT,
                    occurred_at=occurred_at,
                    source_ref=source_ref,
                    weight=1.0,
                    metadata={"ticket_excerpt": ticket_text[:200]},
                )
            )
        return records

    def weight_for_type(self, evidence_type: EvidenceType) -> float:
        if evidence_type == EvidenceType.DEMONSTRATED:
            return self.config.demonstrated_weight
        if evidence_type == EvidenceType.CERTIFIED:
            return self.config.certified_weight
        return self.config.declared_weight

    def freshness_score(self, occurred_at: datetime, as_of: Optional[datetime] = None) -> float:
        now = as_of or datetime.now(timezone.utc)
        days = _days_between(now, occurred_at)
        half = self.config.freshness_half_life_days
        return max(0.0, min(1.0, math.pow(0.5, days / half)))

    def merge_evidence(
        self,
        evidence: Sequence[EvidenceRecord],
        as_of: Optional[datetime] = None,
    ) -> List[SkillRecord]:
        grouped: Dict[Tuple[str, str], List[EvidenceRecord]] = defaultdict(list)
        for item in evidence:
            if item.evidence_type == EvidenceType.DECLARED:
                confirmed = getattr(item, "manager_confirmed", None)
                if confirmed is False:
                    continue
                if confirmed is None and not item.metadata.get("manager_confirmed", True):
                    continue
            grouped[(item.coded_identity, item.skill_id)].append(item)

        results: List[SkillRecord] = []
        for (coded_id, skill_id), items in grouped.items():
            results.append(self._score_group(coded_id, skill_id, items, as_of=as_of))
        return results

    def _score_group(
        self,
        coded_id: str,
        skill_id: str,
        items: Sequence[EvidenceRecord],
        as_of: Optional[datetime] = None,
    ) -> SkillRecord:
        now = as_of or datetime.now(timezone.utc)
        by_type: Dict[EvidenceType, List[EvidenceRecord]] = defaultdict(list)
        for item in items:
            by_type[item.evidence_type].append(item)

        level_scores: Dict[int, float] = defaultdict(float)
        confidence_parts: List[float] = []
        freshness_parts: List[float] = []
        evidence_ids: List[str] = []

        for item in items:
            tw = self.weight_for_type(item.evidence_type)
            fr = self.freshness_score(item.occurred_at, as_of=now)
            contribution = tw * fr * item.weight
            level_scores[int(item.proficiency)] += contribution
            confidence_parts.append(contribution)
            freshness_parts.append(fr)
            evidence_ids.append(item.evidence_id)

        best_level = max(level_scores.items(), key=lambda kv: (kv[1], kv[0]))[0]
        if EvidenceType.DEMONSTRATED in by_type:
            demo_levels = [int(e.proficiency) for e in by_type[EvidenceType.DEMONSTRATED]]
            demo_mode = max(set(demo_levels), key=demo_levels.count)
            if abs(demo_mode - best_level) <= 1:
                best_level = max(best_level, demo_mode)

        total_weight = (
            self.config.demonstrated_weight
            + self.config.certified_weight
            + self.config.declared_weight
        )
        confidence = min(1.0, sum(confidence_parts) / max(total_weight, 1e-9))
        confidence = max(self.config.min_confidence, confidence)
        freshness = sum(freshness_parts) / len(freshness_parts)

        return SkillRecord(
            coded_identity=coded_id,
            skill_id=skill_id,
            proficiency=ProficiencyLevel(best_level),
            confidence=round(confidence, 4),
            freshness=round(freshness, 4),
            evidence_ids=sorted(evidence_ids),
            scoring_config_version=self.config.version,
        )

    def ensure_coverage(self, evidence: Iterable[EvidenceRecord]) -> Mapping[str, int]:
        merged = self.merge_evidence(list(evidence))
        counts: Dict[str, int] = defaultdict(int)
        for record in merged:
            counts[record.coded_identity] += 1
        return dict(counts)

```

### Fitness & Gap Engine (full)

Canonical path: `src/fitness_gap/engine.py`

```python
"""Deterministic fitness ranking and skill-gap computation."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence

from shared.audit import AuditLedger
from shared.config import ScoringConfig, load_scoring_config
from shared.models import (
    FitnessResult,
    GapItem,
    GapResult,
    ProficiencyLevel,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)


class FitnessGapEngine:
    def __init__(
        self,
        config: Optional[ScoringConfig] = None,
        audit: Optional[AuditLedger] = None,
        demand_weights: Optional[Mapping[str, float]] = None,
    ) -> None:
        self.config = config or load_scoring_config()
        self.audit = audit or AuditLedger()
        self.demand_weights = dict(demand_weights or {})

    def rank_candidates(
        self,
        request: StaffingRequest,
        skill_matrix: Sequence[SkillRecord],
        availability: Optional[Mapping[str, bool]] = None,
    ) -> FitnessResult:
        availability = availability or {}
        by_identity: Dict[str, Dict[str, SkillRecord]] = {}
        for record in skill_matrix:
            by_identity.setdefault(record.coded_identity, {})[record.skill_id] = record

        scored: List[RankedCandidate] = []
        for coded_id, skills in by_identity.items():
            if request.availability_required and availability.get(coded_id, True) is False:
                continue
            score, reasoning, evidence_ids = self._fitness(request.required_skills, skills)
            if not evidence_ids:
                # No evidenced match on any required skill — exclude from ranking
                continue
            if request.availability_required and availability.get(coded_id, True):
                score += self.config.availability_bonus
            scored.append(
                RankedCandidate(
                    coded_identity=coded_id,
                    fitness_score=round(score, 4),
                    rank=0,
                    per_skill_reasoning=reasoning,
                    evidence_ids=sorted(set(evidence_ids)),
                )
            )

        scored.sort(key=lambda c: (-c.fitness_score, c.coded_identity))
        shortlist = []
        for idx, cand in enumerate(scored[: request.shortlist_size], start=1):
            shortlist.append(
                RankedCandidate(
                    coded_identity=cand.coded_identity,
                    fitness_score=cand.fitness_score,
                    rank=idx,
                    per_skill_reasoning=cand.per_skill_reasoning,
                    evidence_ids=cand.evidence_ids,
                )
            )

        result = FitnessResult(
            request_id=request.request_id,
            candidates=shortlist,
            scoring_config_version=self.config.version,
        )
        self.audit.append(
            "fitness_ranking",
            actor=request.requester_id,
            payload={
                "request_id": request.request_id,
                "candidate_tokens": [c.coded_identity for c in shortlist],
                "scoring_config_version": self.config.version,
            },
        )
        return result

    def _fitness(
        self,
        required: Mapping[str, ProficiencyLevel],
        skills: Mapping[str, SkillRecord],
    ):
        total = 0.0
        reasoning = {}
        evidence_ids: List[str] = []
        for skill_id, required_level in required.items():
            record = skills.get(skill_id)
            if record is None:
                reasoning[skill_id] = "missing skill evidence"
                continue
            level_ratio = min(1.0, int(record.proficiency) / max(1, int(required_level)))
            contrib = level_ratio * record.confidence * record.freshness
            total += contrib
            reasoning[skill_id] = (
                f"level={int(record.proficiency)}/{int(required_level)} "
                f"confidence={record.confidence:.2f} freshness={record.freshness:.2f} "
                f"evidence={','.join(record.evidence_ids)}"
            )
            evidence_ids.extend(record.evidence_ids)
        if required:
            total = total / len(required)
        return total, reasoning, evidence_ids

    def compute_gaps(
        self,
        coded_identity: str,
        role: TargetRoleProfile,
        skill_matrix: Sequence[SkillRecord],
    ) -> GapResult:
        skills = {
            r.skill_id: r
            for r in skill_matrix
            if r.coded_identity == coded_identity
        }
        gaps: List[GapItem] = []
        for skill_id, required_level in role.required_skills.items():
            record = skills.get(skill_id)
            current = record.proficiency if record else None
            evidence_ids = list(record.evidence_ids) if record else []
            if current is not None and int(current) >= int(required_level):
                continue
            demand = float(self.demand_weights.get(skill_id, 0.5))
            deficit = int(required_level) - (int(current) if current else 0)
            gaps.append(
                GapItem(
                    skill_id=skill_id,
                    required_level=required_level,
                    current_level=current,
                    demand_impact=round(demand * deficit, 4),
                    reasoning=(
                        f"current={int(current) if current else 0} "
                        f"required={int(required_level)} demand={demand}"
                    ),
                    evidence_ids=evidence_ids,
                )
            )
        gaps.sort(key=lambda g: (-g.demand_impact, g.skill_id))
        result = GapResult(
            coded_identity=coded_identity,
            role_id=role.role_id,
            gaps=gaps,
            scoring_config_version=self.config.version,
        )
        self.audit.append(
            "gap_computation",
            actor=coded_identity,
            payload={
                "role_id": role.role_id,
                "gap_skills": [g.skill_id for g in gaps],
                "scoring_config_version": self.config.version,
            },
        )
        return result

```

### Identity Resolution Gateway (full)

Canonical path: `src/identity_resolution/gateway.py`

```python
"""Governed identity resolution for shortlisted candidates only."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Set

from identity_abstraction.gate import IdentityAbstractionGate
from shared.audit import AuditLedger
from shared.models import RankedCandidate


class ResolutionDenied(Exception):
    """Raised when resolution violates gateway policy."""


class IdentityResolutionGateway:
    def __init__(self, gate: IdentityAbstractionGate, audit: Optional[AuditLedger] = None) -> None:
        self._gate = gate
        self._audit = audit or AuditLedger()

    def resolve_shortlist(
        self,
        request_id: str,
        requester_id: str,
        shortlist: Sequence[RankedCandidate],
        allowed_requester_id: str,
    ) -> List[Dict[str, str]]:
        if requester_id != allowed_requester_id:
            raise ResolutionDenied("requester is not authorized for this staffing request")

        allowed: Set[str] = {c.coded_identity for c in shortlist}
        resolved: List[Dict[str, str]] = []
        for candidate in shortlist:
            raw = self._gate.resolve_for_gateway(candidate.coded_identity)
            if raw is None:
                raise ResolutionDenied(f"unknown coded identity: {candidate.coded_identity}")
            if candidate.coded_identity not in allowed:
                raise ResolutionDenied("attempt to resolve non-shortlisted identity")
            resolved.append(
                {
                    "coded_identity": candidate.coded_identity,
                    "display_name": raw,
                    "rank": str(candidate.rank),
                    "fitness_score": str(candidate.fitness_score),
                }
            )

        self._audit.append(
            "identity_resolution",
            actor=requester_id,
            payload={
                "request_id": request_id,
                "resolved_tokens": [r["coded_identity"] for r in resolved],
                "count": len(resolved),
            },
        )
        return resolved

    def resolve_one(
        self,
        request_id: str,
        requester_id: str,
        coded_identity: str,
        shortlist_tokens: Sequence[str],
        allowed_requester_id: str,
    ) -> Mapping[str, str]:
        if requester_id != allowed_requester_id:
            raise ResolutionDenied("requester is not authorized for this staffing request")
        if coded_identity not in set(shortlist_tokens):
            raise ResolutionDenied("coded identity is not on the shortlist")
        raw = self._gate.resolve_for_gateway(coded_identity)
        if raw is None:
            raise ResolutionDenied(f"unknown coded identity: {coded_identity}")
        self._audit.append(
            "identity_resolution",
            actor=requester_id,
            payload={
                "request_id": request_id,
                "resolved_tokens": [coded_identity],
                "count": 1,
            },
        )
        return {"coded_identity": coded_identity, "display_name": raw}

```

### HermesService application wiring (full)

Canonical path: `src/shared/service.py`

```python
"""Application service wiring engines to SQLite for local-first runtime."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fitness_gap.engine import FitnessGapEngine
from identity_abstraction.gate import IdentityAbstractionGate
from identity_resolution.gateway import IdentityResolutionGateway, ResolutionDenied
from shared.audit import AuditLedger
from shared.db import HermesDB
from shared.models import (
    EvidenceRecord,
    ProficiencyLevel,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
)
from skill_inference.engine import SkillInferenceEngine


class HermesService:
    def __init__(self, db: Optional[HermesDB] = None, mapping_secret: Optional[str] = None) -> None:
        self.db = db or HermesDB()
        secret = mapping_secret or os.getenv("IDENTITY_MAP_SECRET", "local-dev-secret")
        self.gate = IdentityAbstractionGate(secret)
        self._hydrate_gate_from_vault()
        self.audit = AuditLedger(db=self.db)
        self.inference = SkillInferenceEngine()
        demand = self.db.get_demand()
        self.fitness = FitnessGapEngine(audit=self.audit, demand_weights=demand)
        self.resolution = IdentityResolutionGateway(self.gate, audit=self.audit)

    def _hydrate_gate_from_vault(self) -> None:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, display_name, source_employee_key FROM identity_vault"
            ).fetchall()
        for row in rows:
            key = row["source_employee_key"]
            token = row["coded_identity"]
            self.gate._forward[key] = token
            self.gate._reverse[token] = key
            self.gate._display_names[token] = row["display_name"]

    def abstract(self, raw: Mapping[str, Any], employee_key_field: str = "employee_id") -> Dict[str, Any]:
        result = self.gate.abstract_record(raw, employee_key_field=employee_key_field)
        self.gate.assert_no_pii(result.record)
        employee_key = str(raw[employee_key_field])
        display = self.gate._display_names.get(result.coded_identity, employee_key)
        self.db.upsert_identity(result.coded_identity, employee_key, display_name=display)
        self.db.set_availability(result.coded_identity, True)
        self.audit.append(
            "evidence_ingestion",
            actor="ingest",
            payload={"coded_identity": result.coded_identity},
        )
        return {
            "coded_identity": result.coded_identity,
            "record": result.record,
            "stripped_fields": list(result.stripped_fields),
        }

    def stage_and_merge(self, evidence: Sequence[EvidenceRecord]) -> List[SkillRecord]:
        for item in evidence:
            # ensure identity exists
            with self.db.session() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM identity_map WHERE coded_identity = ?",
                    (item.coded_identity,),
                ).fetchone()
            if not exists:
                self.db.upsert_identity(item.coded_identity, item.coded_identity, display_name=item.coded_identity)
            self.db.stage_evidence(item)
        all_evidence = self.db.load_all_evidence()
        merged = self.inference.merge_evidence(all_evidence)
        self.db.replace_skills_matrix(merged)
        self.audit.append(
            "inference_computation",
            actor="skill_inference",
            payload={"count": len(merged)},
        )
        return merged

    def rank(self, request: StaffingRequest, availability: Optional[Mapping[str, bool]] = None):
        matrix = self.db.load_skills_matrix()
        avail = dict(self.db.get_availability())
        if availability:
            avail.update(availability)
        self.fitness.demand_weights = self.db.get_demand()
        result = self.fitness.rank_candidates(request, matrix, availability=avail)
        self.db.save_staffing_request(
            request.request_id,
            request.requester_id,
            [c.coded_identity for c in result.candidates],
        )
        return result

    def gaps(self, coded_identity: str, role: TargetRoleProfile):
        matrix = self.db.load_skills_matrix()
        self.fitness.demand_weights = self.db.get_demand()
        return self.fitness.compute_gaps(coded_identity, role, matrix)

    def resolve(self, request_id: str, requester_id: str) -> List[Dict[str, str]]:
        stored = self.db.get_staffing_request(request_id)
        if not stored:
            raise ResolutionDenied("unknown staffing request")
        shortlist = [
            RankedCandidate(
                coded_identity=t,
                fitness_score=0.0,
                rank=i + 1,
                per_skill_reasoning={},
                evidence_ids=[],
            )
            for i, t in enumerate(stored["shortlist"])
        ]
        # Prefer vault display names via gate hydration
        self._hydrate_gate_from_vault()
        return self.resolution.resolve_shortlist(
            request_id=request_id,
            requester_id=requester_id,
            shortlist=shortlist,
            allowed_requester_id=stored["requester_id"],
        )

```

### Domain models & forbidden fields (full)

Canonical path: `src/shared/models.py`

```python
"""Immutable domain models for Hermes. No protected demographic attributes."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class EvidenceType(str, Enum):
    DEMONSTRATED = "demonstrated"
    CERTIFIED = "certified"
    DECLARED = "declared"


class ProficiencyLevel(int, Enum):
    AWARENESS = 1
    WORKING = 2
    PROFICIENT = 3
    ADVANCED = 4
    EXPERT = 5


class CodedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    token: str = Field(..., pattern=r"^EMP-\d{4,}$")


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    coded_identity: str
    skill_id: str
    evidence_type: EvidenceType
    proficiency: ProficiencyLevel
    occurred_at: datetime
    source_ref: str
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DemonstratedEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.DEMONSTRATED


class CertifiedEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.CERTIFIED


class DeclaredEvidence(EvidenceRecord):
    evidence_type: EvidenceType = EvidenceType.DECLARED
    manager_confirmed: bool = True


class SkillRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    skill_id: str
    proficiency: ProficiencyLevel
    confidence: float = Field(..., ge=0.0, le=1.0)
    freshness: float = Field(..., ge=0.0, le=1.0)
    evidence_ids: List[str]
    computed_at: datetime = Field(default_factory=utc_now)
    scoring_config_version: str


class StaffingRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    requester_id: str
    required_skills: Dict[str, ProficiencyLevel]
    shortlist_size: int = 3
    availability_required: bool = True


class TargetRoleProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    role_id: str
    role_name: str
    required_skills: Dict[str, ProficiencyLevel]


class RankedCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    fitness_score: float
    rank: int
    per_skill_reasoning: Dict[str, str]
    evidence_ids: List[str]


class FitnessResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    request_id: str
    candidates: List[RankedCandidate]
    scoring_config_version: str
    computed_at: datetime = Field(default_factory=utc_now)


class GapItem(BaseModel):
    model_config = ConfigDict(frozen=True)

    skill_id: str
    required_level: ProficiencyLevel
    current_level: Optional[ProficiencyLevel]
    demand_impact: float
    reasoning: str
    evidence_ids: List[str]


class GapResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    coded_identity: str
    role_id: str
    gaps: List[GapItem]
    scoring_config_version: str
    computed_at: datetime = Field(default_factory=utc_now)


class AuditEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    actor: str
    payload: Dict[str, Any]
    created_at: datetime = Field(default_factory=utc_now)


PROTECTED_ATTRIBUTE_FIELDS = frozenset(
    {
        "age",
        "gender",
        "ethnicity",
        "race",
        "religion",
        "disability",
        "sexual_orientation",
        "national_origin",
        "marital_status",
        "pregnancy",
        "date_of_birth",
        "dob",
    }
)

IDENTITY_PII_FIELDS = frozenset(
    {
        "name",
        "full_name",
        "first_name",
        "last_name",
        "display_name",
        "email",
        "employee_id",
        "employee_number",
        "user_id",
        "sys_id",
        "upn",
        "sam_account_name",
        "phone",
        "mobile",
    }
)

```

### Scoring config (full)

Canonical path: `src/shared/config.py`

```python
"""Scoring and runtime configuration (versioned for audit ledger)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ScoringConfig:
    version: str
    demonstrated_weight: float
    certified_weight: float
    declared_weight: float
    freshness_half_life_days: float
    availability_bonus: float
    min_confidence: float


DEFAULT_SCORING = ScoringConfig(
    version="1.0.0",
    demonstrated_weight=0.55,
    certified_weight=0.30,
    declared_weight=0.15,
    freshness_half_life_days=180.0,
    availability_bonus=0.05,
    min_confidence=0.1,
)


def load_scoring_config() -> ScoringConfig:
    version = os.getenv("SCORING_CONFIG_VERSION", DEFAULT_SCORING.version)
    return ScoringConfig(
        version=version,
        demonstrated_weight=DEFAULT_SCORING.demonstrated_weight,
        certified_weight=DEFAULT_SCORING.certified_weight,
        declared_weight=DEFAULT_SCORING.declared_weight,
        freshness_half_life_days=DEFAULT_SCORING.freshness_half_life_days,
        availability_bonus=DEFAULT_SCORING.availability_bonus,
        min_confidence=DEFAULT_SCORING.min_confidence,
    )

```


### FastAPI application (full)

Canonical path: `api/main.py`

```python
"""FastAPI local runtime for Hermes judgment components + web UI."""

from __future__ import annotations

import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shared.models import EvidenceRecord, ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.service import HermesService
from shared.taxonomy import load_taxonomy

app = FastAPI(title="Hermes Local API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_SERVICE: Optional[HermesService] = None
WEB_DIST = Path(__file__).resolve().parents[1] / "web" / "dist"


def get_service() -> HermesService:
    global _SERVICE
    if _SERVICE is None:
        db_path = os.getenv("HERMES_DB_PATH")
        from shared.db import HermesDB

        db = HermesDB(Path(db_path) if db_path else None)
        _SERVICE = HermesService(db=db)
    return _SERVICE


def reset_service_for_tests(service: HermesService) -> None:
    global _SERVICE
    _SERVICE = service


def require_api_key(
    x_api_key: Optional[str] = Header(default=None),
    x_functions_key: Optional[str] = Header(default=None),
) -> None:
    expected = os.getenv("HERMES_API_KEY") or os.getenv("FUNCTION_AUTH_KEY") or ""
    if not expected:
        return
    provided = x_api_key or x_functions_key
    if provided != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "service": "hermes", "mode": "local-first"}


@app.get("/api/dashboard")
def dashboard(
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    matrix = svc.db.matrix_records_as_dicts()
    coverage = svc.db.pilot_coverage()
    by_skill: Dict[str, List[float]] = defaultdict(list)
    for row in matrix:
        by_skill[row["skill_id"]].append(float(row["freshness"]))
    freshness = {
        skill: round(sum(vals) / len(vals), 4) if vals else 0.0
        for skill, vals in sorted(by_skill.items())
    }
    return {
        "coverage": coverage,
        "avg_freshness_by_skill": freshness,
        "skill_distribution": [
            {
                "coded_identity": r["coded_identity"],
                "skill_id": r["skill_id"],
                "proficiency": r["proficiency"],
                "confidence": r["confidence"],
                "freshness": r["freshness"],
            }
            for r in matrix
        ],
    }


@app.get("/api/roles")
def list_roles(
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    with svc.db.session() as conn:
        rows = conn.execute("SELECT role_id, role_name, required_skills_json FROM role_profiles").fetchall()
    import json

    roles = [
        {
            "role_id": r["role_id"],
            "role_name": r["role_name"],
            "required_skills": json.loads(r["required_skills_json"]),
        }
        for r in rows
    ]
    return {"roles": roles}


@app.get("/api/skills")
def list_skills(_: None = Depends(require_api_key)) -> Dict[str, Any]:
    tax = load_taxonomy()
    skills = [
        {
            "skill_id": s.skill_id,
            "name": s.name,
            "description": s.description,
            "domain_id": d.domain_id,
            "domain_name": d.name,
        }
        for d in tax.domains
        for s in d.skills
    ]
    return {"skills": skills}


@app.get("/api/identities")
def list_identities(
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    """Coded identities only — no display names."""
    with svc.db.session() as conn:
        rows = conn.execute("SELECT coded_identity FROM identity_map ORDER BY coded_identity").fetchall()
    return {"identities": [r["coded_identity"] for r in rows]}


@app.post("/api/identity/abstract")
def identity_abstract(
    body: Dict[str, Any],
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    try:
        return svc.abstract(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class MergeBody(BaseModel):
    evidence: list


@app.post("/api/inference/merge")
def inference_merge(
    body: MergeBody,
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    evidence = [EvidenceRecord.model_validate(item) for item in body.evidence]
    merged = svc.stage_and_merge(evidence)
    return {"skills": [m.model_dump(mode="json") for m in merged]}


class RankBody(BaseModel):
    request_id: str
    requester_id: str
    required_skills: Dict[str, int]
    shortlist_size: int = 3
    availability_required: bool = True
    availability: Dict[str, bool] = Field(default_factory=dict)


@app.post("/api/fitness/rank")
def fitness_rank(
    body: RankBody,
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    request = StaffingRequest(
        request_id=body.request_id,
        requester_id=body.requester_id,
        required_skills={k: ProficiencyLevel(v) for k, v in body.required_skills.items()},
        shortlist_size=body.shortlist_size,
        availability_required=body.availability_required,
    )
    result = svc.rank(request, availability=body.availability)
    return result.model_dump(mode="json")


class GapBody(BaseModel):
    coded_identity: str
    role_id: str
    role_name: str
    required_skills: Dict[str, int]


@app.post("/api/fitness/gaps")
def fitness_gaps(
    body: GapBody,
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    role = TargetRoleProfile(
        role_id=body.role_id,
        role_name=body.role_name,
        required_skills={k: ProficiencyLevel(v) for k, v in body.required_skills.items()},
    )
    result = svc.gaps(body.coded_identity, role)
    return result.model_dump(mode="json")


class ResolveBody(BaseModel):
    request_id: str
    requester_id: str


@app.post("/api/identity/resolve")
def identity_resolve(
    body: ResolveBody,
    _: None = Depends(require_api_key),
    svc: HermesService = Depends(get_service),
) -> Dict[str, Any]:
    from identity_resolution.gateway import ResolutionDenied

    try:
        resolved = svc.resolve(body.request_id, body.requester_id)
        return {"resolved": resolved}
    except ResolutionDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


# Serve built SPA when present (after API routes so /api wins)
if WEB_DIST.is_dir():
    assets = WEB_DIST / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path == "health":
            raise HTTPException(status_code=404)
        index = WEB_DIST / "index.html"
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(index)
        raise HTTPException(status_code=404, detail="frontend not built")

```


### SQLite schema (full)

Canonical path: `infra/sqlite/001_schema.sql`

```sql
-- Project Hermes SQLite schema (local-first)
-- Classification: Internal, Confidential
-- NOTE: No protected demographic attributes are permitted in this schema.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS identity_map (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    source_hash      TEXT NOT NULL UNIQUE,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

-- Restricted vault: display names for resolution gateway ONLY. Never join into matrix reads.
CREATE TABLE IF NOT EXISTS identity_vault (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    display_name     TEXT NOT NULL,
    source_employee_key TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS evidence_staging (
    evidence_id      TEXT NOT NULL PRIMARY KEY,
    coded_identity   TEXT NOT NULL,
    skill_id         TEXT,
    evidence_type    TEXT NOT NULL CHECK (evidence_type IN ('demonstrated','certified','declared')),
    proficiency      INTEGER CHECK (proficiency IS NULL OR (proficiency BETWEEN 1 AND 5)),
    occurred_at      TEXT NOT NULL,
    source_ref       TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    ingested_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS skills_matrix (
    coded_identity           TEXT NOT NULL,
    skill_id                 TEXT NOT NULL,
    proficiency              INTEGER NOT NULL CHECK (proficiency BETWEEN 1 AND 5),
    confidence               REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    freshness                REAL NOT NULL CHECK (freshness BETWEEN 0 AND 1),
    evidence_ids_json        TEXT NOT NULL,
    scoring_config_version   TEXT NOT NULL,
    computed_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    PRIMARY KEY (coded_identity, skill_id),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS role_profiles (
    role_id          TEXT NOT NULL PRIMARY KEY,
    role_name        TEXT NOT NULL,
    required_skills_json TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS demand_signals (
    skill_id         TEXT NOT NULL PRIMARY KEY,
    demand_weight    REAL NOT NULL CHECK (demand_weight BETWEEN 0 AND 1),
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS availability (
    coded_identity   TEXT NOT NULL PRIMARY KEY,
    is_available     INTEGER NOT NULL DEFAULT 1,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    FOREIGN KEY (coded_identity) REFERENCES identity_map(coded_identity)
);

CREATE TABLE IF NOT EXISTS audit_ledger (
    event_id         TEXT NOT NULL PRIMARY KEY,
    event_type       TEXT NOT NULL,
    actor            TEXT NOT NULL,
    payload_json     TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE TABLE IF NOT EXISTS staffing_requests (
    request_id       TEXT NOT NULL PRIMARY KEY,
    requester_id     TEXT NOT NULL,
    shortlist_json   TEXT NOT NULL DEFAULT '[]',
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
);

CREATE INDEX IF NOT EXISTS IX_audit_type_time ON audit_ledger(event_type, created_at);
CREATE INDEX IF NOT EXISTS IX_evidence_identity ON evidence_staging(coded_identity);
CREATE INDEX IF NOT EXISTS IX_matrix_skill ON skills_matrix(skill_id);

```


### Frontend API client (full)

Canonical path: `web/src/api/client.ts`

```typescript
const headers = (): HeadersInit => {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const key = import.meta.env.VITE_HERMES_API_KEY as string | undefined;
  if (key) h["x-api-key"] = key;
  return h;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { ...init, headers: { ...headers(), ...init?.headers } });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || body.error || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export type Skill = {
  skill_id: string;
  name: string;
  description: string;
  domain_id: string;
  domain_name: string;
};

export type Role = {
  role_id: string;
  role_name: string;
  required_skills: Record<string, number>;
};

export type RankedCandidate = {
  coded_identity: string;
  fitness_score: number;
  rank: number;
  per_skill_reasoning: Record<string, string>;
  evidence_ids: string[];
};

export type FitnessResult = {
  request_id: string;
  candidates: RankedCandidate[];
  scoring_config_version: string;
};

export type GapItem = {
  skill_id: string;
  required_level: number;
  current_level: number | null;
  demand_impact: number;
  reasoning: string;
  evidence_ids: string[];
};

export type GapResult = {
  coded_identity: string;
  role_id: string;
  gaps: GapItem[];
};

export type Resolved = {
  coded_identity: string;
  display_name: string;
  rank: string;
  fitness_score: string;
};

export type Dashboard = {
  coverage: { pilot_size: number; with_demonstrated: number; coverage_pct: number };
  avg_freshness_by_skill: Record<string, number>;
  skill_distribution: Array<{
    coded_identity: string;
    skill_id: string;
    proficiency: number;
    confidence: number;
    freshness: number;
  }>;
};

export const api = {
  skills: () => req<{ skills: Skill[] }>("/api/skills"),
  roles: () => req<{ roles: Role[] }>("/api/roles"),
  identities: () => req<{ identities: string[] }>("/api/identities"),
  dashboard: () => req<Dashboard>("/api/dashboard"),
  rank: (body: {
    request_id: string;
    requester_id: string;
    required_skills: Record<string, number>;
    shortlist_size?: number;
  }) =>
    req<FitnessResult>("/api/fitness/rank", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  gaps: (body: {
    coded_identity: string;
    role_id: string;
    role_name: string;
    required_skills: Record<string, number>;
  }) =>
    req<GapResult>("/api/fitness/gaps", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  resolve: (body: { request_id: string; requester_id: string }) =>
    req<{ resolved: Resolved[] }>("/api/identity/resolve", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

```


---

## 18. Frontend page & component inventory

| File | Role |
|------|------|
| `web/src/main.tsx` | React root + BrowserRouter |
| `web/src/App.tsx` | Nav + AnimatePresence routes |
| `web/src/pages/Entry.tsx` | Brand hero |
| `web/src/pages/Staff.tsx` | Rank + resolve flow |
| `web/src/pages/Learn.tsx` | Gap flow |
| `web/src/pages/Matrix.tsx` | Coverage / heatmap |
| `web/src/components/BrandMark.tsx` | Animated HERMES letters |
| `web/src/components/ScoreMeter.tsx` | Animated fitness bar |
| `web/src/components/ShortlistReveal.tsx` | Staggered shortlist + name morph |
| `web/src/components/GapCascade.tsx` | Demand gap bars |
| `web/src/components/CoverageRing.tsx` | SVG coverage ring |
| `web/src/components/SkillHeatmap.tsx` | Coded-only heatmap |
| `web/src/components/NarrateBanner.tsx` | Rules/approval notice |
| `web/src/motion/presets.ts` | Shared motion + reduced-motion |
| `web/src/styles/tokens.css` | Design tokens / atmosphere |
| `web/vite.config.ts` | Dev proxy `/api` → `:8000` |

For full UI source, open those paths in the repo (quoted engines + API above are the judgment core).

---

## 19. Scripts reference

| Command | What it does |
|---------|----------------|
| `python -m scripts.ingest_fixtures` | Rebuild SQLite from pilot fixtures |
| `python -m scripts.seed_local_matrix` | Wrapper around ingest |
| `python -m scripts.hermes_query staff --skills X --level N [--resolve]` | CLI staffing |
| `python -m scripts.hermes_query gaps EMP-#### --role ROLE` | CLI gaps |
| `python -m scripts.dashboard_export` | Write `data/reports/dashboard.html` |
| `python -m scripts.leakage_audit` | Fail on PII in matrix sample |
| `python -m scripts.fairness_audit` | Fail if protected columns in schema |
| `python -m scripts.coverage_report` | Pilot demonstrated coverage % |

---

## 20. Decision log (locked for this MVP)

1. **Local-first** — no Azure required to run.  
2. **Full hybrid repo layout** retained — Power Platform/Bicep stubs for future.  
3. **FastAPI** replaces Azure Functions for local HTTP.  
4. **SQLite** replaces Azure SQL.  
5. **React animated console** is the primary human UI; CLI secondary.  
6. **Fixtures** stand in for ServiceNow/LMS/HR until connectors are authorized.  

---

## 21. Handoff checklist for another AI / new engineer

1. Read this bible end-to-end.  
2. Open and skim: `src/shared/service.py`, `api/main.py`, `web/src/App.tsx`.  
3. Run ingest + pytest + `npm run build` in `web/`.  
4. Manually hit `/staff` and `/learn` against live API.  
5. Never add protected attributes or auto-assignment.  
6. Never show names on Matrix or in scoring payloads.  
7. Prefer extending engines with tests first (TDD).  

---

## 22. Related docs in-repo

- `README.md` — quick start  
- `docs/architecture.md` — layer summary  
- `docs/mvp-success-criteria.md` — metrics  
- `docs/mvp-validation-report.md` — validation status  
- `docs/evidence-merge-rules.md` — merge rules  
- `docs/future-azure.md` — future cloud path  
- `docs/runbooks/local-dev.md` — local ops  
- `docs/runbooks/source-connectors.md` — future field catalogue  
- `docs/adrs/001-hybrid-build.md` — hybrid ADR  
- `web/README.md` — frontend DX  

---

*End of PROJECT BIBLE. If something in the repo disagrees with a prose claim above, trust the executable tests and source files.*

## Legal / EU AI Act and consultation

### High-risk posture

Hermes supports **employment / task-allocation** recommendations. Under the EU AI Act
Annex III, systems used for recruitment or for decisions affecting terms of work /
task allocation may be classified as **high-risk**. Treat Hermes as high-risk-by-default
for EU staff in scope until legal confirms otherwise.

### Required artefacts (living)

| Artefact | Location / owner |
|---|---|
| Technical documentation | This bible + `docs/architecture.md` |
| Bias / impact testing | `docs/bias-audit-methodology.md`, `scripts/impact_audit.py` (HR-held; not in ops path) |
| Human oversight evidence | Staffing decision endpoint `POST /api/staffing/{id}/decision` + integrity-chained audit ledger |
| Transparency | Coded-identity UI; resolve gateway; explainability `reasoning_detail` |
| Risk register | `docs/risk-register.md` |

### Works council / consultation

If EU employees are in pilot scope, **works-council or equivalent consultation obligations
may already be live** before production use. Product must not auto-assign; managers retain
accept / reject / override. Legal and Employee Relations own consultation sequencing.

### Guardrails (reaffirmed)

1. Recommendation-only — no auto-assignment  
2. No protected demographics in schema or features  
3. Names only via audited resolution gateway  
4. Evidence required for fitness claims  
5. Fail-closed secrets outside test mode  
6. Gaps subject-bound (self / manager edge / admin+audit)  
7. Integrity-chained audit log (not yet external WORM)  
8. **Never score on historical staffing decisions**

### Softened audit language

Until an external WORM sink exists, describe the ledger as an **integrity-chained audit log**,
not integrity-chained WORM storage.


## Phase 8 — Real data integration (decision log entry)

| Decision | Choice |
|---|---|
| D1 | `0.0` baseline = NOT ASSESSED (`normalised_level` NULL) |
| D2 | Client-named columns → `account_context` only, never fitness |
| D3 | Soft-skill columns excluded; `culture fit` raises via classifier |
| D4 | 2025 matrix is BASELINE only — isolated from scoring |

### New tables (section 6 addendum)

- `account_context` — account familiarity; never scoring
- `baseline_assessments` — manager-assessed baseline; never scoring
- `skill_aliases` / `manager_aliases` — pending until `mapped_by=human`
- `cert_staging` — certificates with nullable `earned_at`

### New guardrails (section 4 addendum)

- Client-name blocklist (`config/client_names.txt`)
- Soft-skill exclusion log (`data/reports/phase8_exclusions.json`)
- Baseline isolation test (`tests/guardrails/test_baseline_isolation.py`)
- Guardrail 8 remains: never score on historical staffing decisions

### New scripts (section 19 addendum)

- `scripts/phase8/extract_labels.py`
- `scripts/phase8/generate_template_v2.py`
- `scripts/phase8/ingest_baseline.py`
- `scripts/phase8/ingest_certificates.py`
- `scripts/phase8/promote_certs.py`
- `scripts/phase8/baseline_agreement.py`

