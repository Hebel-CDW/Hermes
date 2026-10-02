"""Read-only presentation models for the Hermes UI.

Every figure here is derived server-side from stored rows (skills_matrix, identity_map,
staffing_requests, audit_ledger). Nothing is scored or ranked here — fitness, volume,
contribution and ranking come only from the engines and are served verbatim from the
stored ranking result. The UI renders these values; it does not recompute them.

No function in this module writes to the database or the audit ledger.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from shared.config import ScoringConfig
from shared.db import HermesDB
from shared.taxonomy import SkillsTaxonomy


def _mean(values: List[float]) -> Optional[float]:
    return round(sum(values) / len(values), 4) if values else None


def _skill_domain(taxonomy: SkillsTaxonomy) -> Dict[str, Dict[str, str]]:
    return {
        s.skill_id: {"domain_id": d.domain_id, "domain_name": d.name, "name": s.name}
        for d in taxonomy.domains
        for s in d.skills
    }


def _matrix(db: HermesDB) -> List[Dict[str, Any]]:
    return sorted(db.matrix_records_as_dicts(), key=lambda r: (r["coded_identity"], r["skill_id"]))


def _people(db: HermesDB) -> List[str]:
    with db.session() as conn:
        return [r["coded_identity"] for r in conn.execute("SELECT coded_identity FROM identity_map ORDER BY 1")]


def overview(db: HermesDB, taxonomy: SkillsTaxonomy, config: ScoringConfig) -> Dict[str, Any]:
    matrix = _matrix(db)
    people = _people(db)
    domains = _skill_domain(taxonomy)
    with_evidence = sorted({r["coded_identity"] for r in matrix})
    by_domain: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in matrix:
        by_domain[domains[row["skill_id"]]["domain_id"]].append(row)
    domain_rows = []
    for d in taxonomy.domains:
        rows = by_domain.get(d.domain_id, [])
        holders = sorted({r["coded_identity"] for r in rows})
        domain_rows.append(
            {
                "domain_id": d.domain_id,
                "name": d.name,
                "skill_count": len(d.skills),
                "skill_records": len(rows),
                "identities_with_evidence": len(holders),
                "coverage_ratio": round(len(holders) / len(people), 4) if people else None,
                "mean_level": _mean([float(r["proficiency"]) for r in rows]),
                "mean_confidence": _mean([float(r["confidence"]) for r in rows]),
                "mean_freshness": _mean([float(r["freshness"]) for r in rows]),
            }
        )
    with db.session() as conn:
        events = conn.execute(
            "SELECT seq, event_type, created_at FROM audit_ledger ORDER BY seq DESC LIMIT 8"
        ).fetchall()
        request_counts = {
            r["status"]: r["n"]
            for r in conn.execute("SELECT status, COUNT(*) AS n FROM staffing_requests GROUP BY status")
        }
        roles = conn.execute("SELECT COUNT(*) AS n FROM role_profiles").fetchone()["n"]
    runs = db.list_computation_runs()
    return {
        "people": len(people),
        "identities_with_evidence": len(with_evidence),
        "skill_coverage_ratio": round(len(with_evidence) / len(people), 4) if people else None,
        "demonstrated_coverage": db.pilot_coverage(),
        "governed_skills": len(taxonomy.all_skills()),
        "skill_records": len(matrix),
        "role_profiles": roles,
        "requests_by_status": dict(sorted(request_counts.items())),
        "domains": domain_rows,
        "recent_activity": [dict(e) for e in events],
        "scoring_config_version": config.version,
        "latest_computation_run_id": runs[0] if runs else None,
        "audit_chain_verified": db.verify_audit_chain() == [],
        "data_classification": db.get_meta("data_classification"),
    }


def workforce(db: HermesDB, taxonomy: SkillsTaxonomy) -> Dict[str, Any]:
    domains = _skill_domain(taxonomy)
    by_identity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for row in _matrix(db):
        by_identity[row["coded_identity"]].append(
            {
                "skill_id": row["skill_id"],
                "skill_name": domains[row["skill_id"]]["name"],
                "domain_id": domains[row["skill_id"]]["domain_id"],
                "proficiency": int(row["proficiency"]),
                "confidence": float(row["confidence"]),
                "freshness": float(row["freshness"]),
                "volume_score": float(row["volume_score"]),
            }
        )
    identities = []
    for coded in _people(db):
        skills = by_identity.get(coded, [])
        identities.append(
            {
                "coded_identity": coded,
                "skill_count": len(skills),
                "domains": sorted({s["domain_id"] for s in skills}),
                "primary_domain": max(
                    sorted({s["domain_id"] for s in skills}),
                    key=lambda dom: sum(1 for s in skills if s["domain_id"] == dom),
                    default=None,
                ),
                "mean_confidence": _mean([s["confidence"] for s in skills]),
                "mean_freshness": _mean([s["freshness"] for s in skills]),
                "max_level": max((s["proficiency"] for s in skills), default=None),
                "skills": skills,
            }
        )
    return {
        "identities": identities,
        "domains": [{"domain_id": d.domain_id, "name": d.name} for d in taxonomy.domains],
    }


def skill_summary(
    db: HermesDB, taxonomy: SkillsTaxonomy, config: ScoringConfig, skill_id: str
) -> Optional[Dict[str, Any]]:
    skill = taxonomy.skill_by_id(skill_id)
    if skill is None:
        return None
    domains = _skill_domain(taxonomy)
    people = _people(db)
    rows = [r for r in _matrix(db) if r["skill_id"] == skill_id]
    levels = {str(level): 0 for level in range(1, 6)}
    for r in rows:
        levels[str(int(r["proficiency"]))] += 1
    effective = dict(config.effective_half_lives)
    all_rows = _matrix(db)
    related = sorted(set(skill.related_skills) | set(skill.relations))
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "domain_id": domains[skill_id]["domain_id"],
        "domain_name": domains[skill_id]["domain_name"],
        "decay_class": skill.decay_class,
        "effective_half_life_days": effective.get(skill_id),
        "proficiency_levels": [
            {"level": int(p.level), "label": p.label, "definition": p.behavioural_definition}
            for p in skill.proficiency_levels
        ],
        "workforce_size": len(people),
        "identities_with_evidence": len(rows),
        "coverage_ratio": round(len(rows) / len(people), 4) if people else None,
        "level_distribution": levels,
        "mean_level": _mean([float(r["proficiency"]) for r in rows]),
        "mean_confidence": _mean([float(r["confidence"]) for r in rows]),
        "mean_freshness": _mean([float(r["freshness"]) for r in rows]),
        "holders": [
            {
                "coded_identity": r["coded_identity"],
                "proficiency": int(r["proficiency"]),
                "confidence": float(r["confidence"]),
                "freshness": float(r["freshness"]),
                "volume_score": float(r["volume_score"]),
            }
            for r in rows
        ],
        "related_skills": [
            {
                "skill_id": rid,
                "name": domains[rid]["name"] if rid in domains else rid,
                "identities_with_evidence": sum(1 for r in all_rows if r["skill_id"] == rid),
            }
            for rid in related
        ],
    }


def request_summary(stored: Dict[str, Any]) -> Dict[str, Any]:
    result = stored.get("result") or {}
    return {
        "request_id": stored["request_id"],
        "owner": stored["requester_id"],
        "status": stored["status"],
        "created_at": stored.get("created_at"),
        "requirements": stored.get("requirements") or {},
        "candidate_count": len(result.get("candidates") or stored.get("shortlist") or []),
        "excluded_count": len(stored.get("excluded") or []),
        "decision": {
            "status": stored["status"] if stored["status"] != "open" else None,
            "approved_by": stored.get("approved_by"),
            "decided_at": stored.get("decided_at"),
            "chosen_coded_identity": stored.get("chosen_coded_identity"),
            "engine_rank_of_choice": stored.get("engine_rank_of_choice"),
        },
        "scoring_config_version": result.get("scoring_config_version"),
        "computation_run_id": result.get("computation_run_id") or stored.get("computation_run_id"),
    }


def data_quality(db: HermesDB, taxonomy: SkillsTaxonomy) -> Dict[str, Any]:
    """Governed data-quality and pipeline-state model (aggregate counts only).

    Distinguishes IMPORTED (coded identities), VALIDATED (accepted workbook cells),
    MAPPED (labels with a governed canonical skill), PENDING (labels awaiting human
    taxonomy approval) and SCORED (identities with evidence-derived skill records).
    Baseline workbook ratings are never scored, so a real workbook with no governed
    mappings and no dated evidence reports 0 scored — by construction, not by display.

    Never returns names, raw workbook rows, account/client labels or vault contents.
    The only labels returned are canonical-mapping traces for skill labels.
    """
    with db.session() as conn:
        # sqlite3.Row supports both row[0] and row["col"]; psycopg2's
        # RealDictCursor rows (used for the PostgreSQL dialect) support only
        # key access — found live, via a real Postgres test-parity run, not
        # assumed. dict(row).values() works identically for both.
        one = lambda sql: int(next(iter(dict(conn.execute(sql).fetchone()).values())))  # noqa: E731
        counts = {
            "people_imported": one("SELECT COUNT(*) FROM identity_map"),
            "people_with_baseline": one("SELECT COUNT(DISTINCT coded_identity) FROM baseline_assessments"),
            "baseline_rows": one("SELECT COUNT(*) FROM baseline_assessments"),
            "baseline_rows_mapped": one(
                "SELECT COUNT(*) FROM baseline_assessments WHERE skill_id IS NOT NULL AND skill_id != ''"
            ),
            "baseline_not_assessed": one("SELECT COUNT(*) FROM baseline_assessments WHERE normalised_level IS NULL"),
            "account_context_rows": one("SELECT COUNT(*) FROM account_context"),
            "pending_aliases": one("SELECT COUNT(*) FROM skill_aliases WHERE mapped_by = 'pending'"),
            "approved_aliases": one(
                "SELECT COUNT(*) FROM skill_aliases WHERE mapped_by IN ('auto','human') AND skill_id != ''"
            ),
            "scored_people": one("SELECT COUNT(DISTINCT coded_identity) FROM skills_matrix"),
            "skill_records": one("SELECT COUNT(*) FROM skills_matrix"),
            "evidence_records": one("SELECT COUNT(*) FROM evidence_staging"),
            "certificates_staged": one("SELECT COUNT(*) FROM cert_staging"),
            "certificates_exact_mapped": one(
                "SELECT COUNT(*) FROM cert_staging WHERE cert_code IS NOT NULL AND cert_code != ''"
            ),
            "certificates_with_earned_at": one("SELECT COUNT(*) FROM cert_staging WHERE earned_at IS NOT NULL"),
            "certificates_promoted": one("SELECT COUNT(*) FROM cert_staging WHERE promoted = 1"),
        }
        level_rows = conn.execute(
            "SELECT normalised_level AS lvl, COUNT(*) AS n FROM baseline_assessments GROUP BY normalised_level"
        ).fetchall()
    run = db.latest_ingest_run()
    summary = run["summary"] if run else None
    labels = (summary or {}).get("labels") or {}
    cells = (summary or {}).get("cells") or {}
    certs = counts["certificates_staged"]
    return {
        "data_classification": db.get_meta("data_classification"),
        "canonical_skills": len(taxonomy.all_skills()),
        "ingestion": None
        if run is None
        else {
            "run_id": run["run_id"],
            "source_name": run["source_name"],
            "ingested_at": run["ingested_at"],
            "sheets": summary.get("sheets"),
            "people_detected": summary.get("people_detected"),
            "cells_processed": cells.get("processed"),
            "cells_accepted": cells.get("accepted"),
            "cells_rejected": cells.get("rejected"),
            "accepted_skill_cells": cells.get("accepted_skill_cells"),
            "accepted_account_cells": cells.get("accepted_account_cells"),
            "rejections_by_reason": cells.get("rejections_by_reason", {}),
            "labels": {
                "skill_labels": labels.get("skill_labels"),
                "mapped": labels.get("mapped"),
                "pending": labels.get("pending"),
                "rejected": labels.get("rejected", {}),
                "mapped_trace": labels.get("mapped_trace", []),
            },
            "excluded_field_occurrences": summary.get("excluded_field_occurrences", {}),
            "certificates": summary.get("certificates", {}),
        },
        "database": counts,
        "baseline_level_distribution": {
            ("not_assessed" if r["lvl"] is None else f"level_{r['lvl']}"): int(r["n"]) for r in level_rows
        },
        "certificates": {
            "staged": certs,
            "exact_mapped": counts["certificates_exact_mapped"],
            "pending": certs - counts["certificates_exact_mapped"],
            "with_earned_at": counts["certificates_with_earned_at"],
            "promoted": counts["certificates_promoted"],
        },
        "pipeline": {
            "imported": counts["people_imported"],
            "validated": cells.get("accepted"),
            "mapped": labels.get("mapped"),
            "pending": labels.get("pending"),
            "scored": counts["scored_people"],
        },
        "activation_status": _activation_status(counts, run),
    }


#: Ordered so a UI can render progress without its own state machine.
ACTIVATION_STATES = (
    "NOT_READY",
    "INGESTED",
    "GOVERNANCE_PENDING",
    "PARTIALLY_ACTIVE",
    "ACTIVE",
    "VALIDATED",
)


def _activation_status(counts: Dict[str, int], run: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive the real-data activation state from stored counts alone (Phase 5).

    ``skills_matrix`` row count (``counts["scored_people"]``) is the hard technical
    gate: nothing below ever reports ACTIVE or VALIDATED while it is zero, no
    matter how much staging or governance work has happened. ``VALIDATED`` is
    never auto-derived here — it requires an explicit human sign-off event (e.g. a
    completed manager-agreement run) this function cannot observe from counts
    alone, so the highest state it can return on its own is ACTIVE.
    """
    if run is None:
        return {
            "state": "NOT_READY", "reason": "No workbook has been ingested yet.",
            "scored_people": 0, "real_data_active": False,
        }

    certs_outstanding = counts["certificates_staged"] - counts["certificates_promoted"]
    blockers = []
    if counts["pending_aliases"] > 0:
        blockers.append(f"{counts['pending_aliases']} skill label(s) awaiting taxonomy mapping")
    if certs_outstanding > 0:
        blockers.append(f"{certs_outstanding} certificate(s) not yet promoted")

    scored = counts["scored_people"]
    if scored == 0:
        # REAL_DATA_ACTIVE is hard-wired to False on this branch — not computed from
        # `state` — so a future new state value can never accidentally flip it true
        # while skills_matrix is still empty. This is the exact property the V3
        # directive calls out by name as a required production check.
        return {
            "state": "GOVERNANCE_PENDING" if blockers else "INGESTED",
            "reason": "; ".join(blockers) if blockers else "Workbook ingested; no governed evidence staged yet.",
            "scored_people": 0,
            "real_data_active": False,
        }
    if blockers:
        return {
            "state": "PARTIALLY_ACTIVE",
            "reason": f"{scored} of {counts['people_imported']} people scoreable; " + "; ".join(blockers),
            "scored_people": scored,
            "real_data_active": True,
        }
    return {
        "state": "ACTIVE",
        "reason": f"{scored} of {counts['people_imported']} people have governed, scoreable evidence.",
        "scored_people": scored,
        "real_data_active": True,
    }


def cert_governance_queue(db: HermesDB, taxonomy: SkillsTaxonomy) -> Dict[str, Any]:
    """Per-certificate triage queue: exactly what blocks each cert from promotion.

    Read-only view backing the admin cert-governance workflow (Phase 2 Step A/B).
    Never returns a person's real name — ``coded_identity`` only, same as every
    other read model in this module. Already-promoted certs are counted but
    omitted from ``items`` since there is nothing left to action on them.
    """
    from shared.excel_sunset import map_cert_label

    code_to_skill = {
        code: skill.skill_id for skill in taxonomy.all_skills() for code in skill.cert_codes
    }
    with db.session() as conn:
        rows = [
            dict(r)
            for r in conn.execute(
                "SELECT staging_id, coded_identity, cert_label, cert_code, earned_at, promoted "
                "FROM cert_staging ORDER BY staging_id"
            ).fetchall()
        ]

    counts = {"needs_date": 0, "needs_mapping": 0, "ready_to_promote": 0, "promoted": 0}
    items: List[Dict[str, Any]] = []
    for row in rows:
        if int(row["promoted"] or 0) == 1:
            counts["promoted"] += 1
            continue
        skill_id, cert_code = map_cert_label(db, row["cert_label"], code_to_skill)
        has_date = bool((row["earned_at"] or "").strip())
        has_mapping = bool(skill_id)
        if has_date and has_mapping:
            status = "ready_to_promote"
            counts["ready_to_promote"] += 1
        elif not has_date and not has_mapping:
            status = "needs_date_and_mapping"
            counts["needs_date"] += 1
            counts["needs_mapping"] += 1
        elif not has_date:
            status = "needs_date"
            counts["needs_date"] += 1
        else:
            status = "needs_mapping"
            counts["needs_mapping"] += 1
        items.append(
            {
                "staging_id": row["staging_id"],
                "coded_identity": row["coded_identity"],
                "cert_label": row["cert_label"],
                "resolved_skill_id": skill_id or "",
                "resolved_cert_code": cert_code or "",
                "status": status,
            }
        )
    return {"counts": counts, "items": items}
