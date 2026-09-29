#!/usr/bin/env python3
"""Deterministic SVP demonstration — the full Hermes pipeline in 14 observable steps.

Determinism contract
--------------------
Two things would otherwise make a run drift:

* **freshness** decays against wall-clock time  → pinned with ``AS_OF``
* **computation_run_id** is a ``uuid4()``       → pinned with ``RUN_ID``

With both pinned, and given the same fixture, taxonomy, and scoring config, every
number below is byte-reproducible. ``--verify`` runs the pipeline twice into two
separate databases and asserts the transcripts are identical.

Data classification
-------------------
This demo uses **SYNTHETIC DATA** only (``data/fixtures/pilot_population.json``,
people E1001-E1005). It touches no real employee, no client account, and no
baseline rating. See ``docs/DATA_LINEAGE.md`` §11.

Usage
-----
    python -m scripts.demo_svp                 # run, print transcript
    python -m scripts.demo_svp --verify        # prove reproducibility
    python -m scripts.demo_svp --json          # machine-readable transcript
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from shared.db import HermesDB  # noqa: E402
from shared.models import ProficiencyLevel, StaffingRequest, TargetRoleProfile  # noqa: E402
from shared.service import HermesService  # noqa: E402

# --- Determinism anchors -------------------------------------------------
AS_OF = datetime(2026, 9, 1, tzinfo=timezone.utc)
RUN_ID = "demo-run-0001"
RUN_ID_2 = "demo-run-0002"  # second pinned run, to demonstrate recalculation
REQUEST_ID = "demo-k8s-migration"
REQUESTER = "demo-manager"  # synthetic registry principal
FIXTURE = ROOT / "data" / "fixtures" / "pilot_population.json"

# The incoming staffing request the demo dramatises.
REQUIRED_SKILLS = {"container_orchestration": 3, "azure_networking": 2}
TARGET_ROLE = "senior_cloud_engineer"


def _rebuild(db_path: Path) -> HermesService:
    """Ingest the synthetic fixture, then recompute the matrix at a pinned clock."""
    from scripts.ingest_fixtures import ingest

    if db_path.exists():
        db_path.unlink()
    ingest(FIXTURE, db_path, write_samples=False)  # never rewrites tracked fixtures
    svc = HermesService(db=HermesDB(db_path))
    # Re-merge everything already staged, this time against the pinned as_of and
    # a fixed run id, so freshness (and therefore every score) is reproducible.
    svc.stage_and_merge([], as_of=AS_OF, computation_run_id=RUN_ID)
    return svc


def run(db_path: Path) -> Dict[str, Any]:
    """Execute the 14 demo steps and return a structured transcript."""
    svc = _rebuild(db_path)
    steps: List[Dict[str, Any]] = []

    def step(n: int, title: str, payload: Any) -> None:
        steps.append({"step": n, "title": title, "detail": payload})

    # 1 — Incoming staffing request
    step(1, "Incoming staffing request", {
        "request_id": REQUEST_ID,
        "requester": REQUESTER,
        "narrative": "Kubernetes migration for a regulated workload; needs networking too.",
    })

    # 2 — Required skills
    step(2, "Required skills", {
        "required_skills": REQUIRED_SKILLS,
        "note": "Levels are ontology levels 1-5 with behavioural definitions.",
    })

    # 3 — Evidence collection
    evidence_rows = svc.db.load_all_evidence()
    by_type: Dict[str, int] = {}
    for e in evidence_rows:
        by_type[e.evidence_type.value] = by_type.get(e.evidence_type.value, 0) + 1
    step(3, "Evidence collection", {
        "total_evidence_rows": len(evidence_rows),
        "by_type": dict(sorted(by_type.items())),
        "note": "Only matched_keywords and source_ref persist - never ticket text.",
    })

    # 4 — Skill inference
    matrix = svc.db.load_skills_matrix()
    step(4, "Skill inference", {
        "matrix_rows": len(matrix),
        "computation_run_id": RUN_ID,
        "as_of": AS_OF.isoformat(),
        "sample": [
            {
                "coded_identity": m.coded_identity,
                "skill_id": m.skill_id,
                "proficiency": int(m.proficiency),
                "confidence": m.confidence,
                "volume_score": m.volume_score,
                "freshness": m.freshness,
            }
            for m in sorted(matrix, key=lambda r: (r.coded_identity, r.skill_id))
        ],
    })

    # 5 — Candidate ranking
    result = svc.rank(
        StaffingRequest(
            request_id=REQUEST_ID,
            requester_id=REQUESTER,
            required_skills={k: ProficiencyLevel(v) for k, v in REQUIRED_SKILLS.items()},
            shortlist_size=3,
        ),
        min_coverage_ratio=0.5,
    )
    step(5, "Candidate ranking", {
        "scoring_config_version": result.scoring_config_version,
        "shortlist": [
            {"rank": c.rank, "coded_identity": c.coded_identity, "fitness_score": c.fitness_score}
            for c in result.candidates
        ],
        "excluded_candidates": result.excluded_candidates,
    })

    # 6 — Calculation inspector
    top = result.candidates[0] if result.candidates else None
    step(6, "Calculation inspector", {
        "coded_identity": top.coded_identity if top else None,
        "calculation": top.calculation.model_dump() if top and top.calculation else None,
        "per_skill": top.reasoning_detail if top else None,
    })

    # 7 — Evidence drill-down
    step(7, "Evidence drill-down", {
        "coded_identity": top.coded_identity if top else None,
        "evidence_ids": top.evidence_ids if top else [],
        "source_refs": sorted(
            {r for d in (top.reasoning_detail or {}).values() for r in (d.get("source_refs") or [])}
        ) if top else [],
    })

    # 8 — Identity remains coded
    step(8, "Identity remains coded", {
        "shortlist_tokens": [c.coded_identity for c in result.candidates],
        "names_present": False,
        "note": "Nothing above this line has joined identity_vault.",
    })

    # 9 — Controlled identity resolution
    resolved = svc.resolve(REQUEST_ID, REQUESTER)
    step(9, "Controlled identity resolution", {
        "resolved_count": len(resolved),
        "resolved": resolved,
        "controls": [
            "requester must own the request",
            "shortlist-only",
            "10/min rate limit",
            "audited",
        ],
    })

    # 10 — Manager decision
    chosen = result.candidates[0].coded_identity if result.candidates else None
    decision = svc.decide(
        request_id=REQUEST_ID,
        approved_by=REQUESTER,
        status="accepted",
        chosen_coded_identity=chosen,
    )
    step(10, "Manager decision", {
        "status": decision.get("status"),
        "approved_by": decision.get("approved_by"),
        "chosen_coded_identity": decision.get("chosen_coded_identity"),
        "engine_rank_of_choice": decision.get("engine_rank_of_choice"),
        "note": "Recorded for audit only - never read back into scoring (Guardrail 8).",
    })

    # 11 — Audit event
    with svc.db.session() as conn:
        rows = conn.execute(
            "SELECT event_type, actor FROM audit_ledger ORDER BY created_at, event_id"
        ).fetchall()
    chain_errors = svc.db.verify_audit_chain()
    counts: Dict[str, int] = {}
    for r in rows:
        counts[r["event_type"]] = counts.get(r["event_type"], 0) + 1
    step(11, "Audit event", {
        "ledger_events": len(rows),
        "by_type": dict(sorted(counts.items())),
        "chain_verified": not chain_errors,
        "chain_errors": chain_errors,
    })

    # 12 — Skill gap
    role = svc.db.get_role(TARGET_ROLE)
    gaps = svc.gaps(
        chosen,
        TargetRoleProfile(
            role_id=role["role_id"],
            role_name=role["role_name"],
            required_skills={k: ProficiencyLevel(v) for k, v in role["required_skills"].items()},
        ),
    )
    step(12, "Skill gap", {
        "coded_identity": chosen,
        "role_id": gaps.role_id,
        "gaps": [
            {
                "skill_id": g.skill_id,
                "current_level": int(g.current_level) if g.current_level else None,
                "required_level": int(g.required_level),
                "demand_impact": g.demand_impact,
            }
            for g in gaps.gaps
        ],
    })

    # 13 — Learning recommendation
    step(13, "Learning recommendation", {
        "ordered_path": [g.skill_id for g in gaps.gaps],
        "basis": "demand_impact = demand_weight x deficit (SCORING_SPECIFICATION.md section 6)",
        "note": "Ordered by organisational value of closing the gap, not gap size alone.",
    })

    # 14 — Matrix history / recalculation
    # Recompute under a second pinned run id to demonstrate a real recalculation.
    svc.stage_and_merge([], as_of=AS_OF, computation_run_id=RUN_ID_2)
    all_runs = svc.db.list_computation_runs()
    pinned = sorted(r for r in all_runs if r.startswith("demo-run-"))
    replay_1 = svc.db.load_matrix_as_of(RUN_ID)
    replay_2 = svc.db.load_matrix_as_of(RUN_ID_2)
    step(14, "Matrix history / recalculation", {
        "pinned_runs": pinned,
        "history_rows_run_1": len(replay_1),
        "history_rows_run_2": len(replay_2),
        "recalculation_is_stable": (
            sorted((r["coded_identity"], r["skill_id"], r["proficiency"]) for r in replay_1)
            == sorted((r["coded_identity"], r["skill_id"], r["proficiency"]) for r in replay_2)
        ),
        "bootstrap_runs_with_uuid_ids": len(all_runs) - len(pinned),
        "note": (
            "Every recompute closes the prior history window and is replayable by run id. "
            "The demo pins run ids; the bootstrap ingest still mints a uuid4 - a tracked "
            "AMBER limitation (see V2_READINESS_REPORT.md)."
        ),
    })

    safeguards = _safeguards(db_path, top.coded_identity if top else None)

    return {
        "demo": "hermes-svp",
        "data_classification": "SYNTHETIC",
        "safeguards": safeguards,
        "as_of": AS_OF.isoformat(),
        "computation_run_id": RUN_ID,
        "scoring_config_version": result.scoring_config_version,
        "steps": steps,
    }


# ---------------------------------------------------------------------------
# Safeguards: every control the SVP is likely to probe, demonstrated live.
# Only status codes, reason codes and counts are recorded — never names — so the
# section is deterministic and safe to show.
# ---------------------------------------------------------------------------

def _safeguards(db_path: Path, top_candidate) -> Dict[str, Any]:
    import shutil
    import tempfile

    from fastapi.testclient import TestClient

    import api.main as api_main
    from phase8.aliases import SkillAliasResolver, ontology_lookup_map
    from shared.db_trust import assess_database_trust
    from shared.secrets import (
        PUBLISHED_SECRETS,
        require_real_data_ingest_secret,
        validate_real_data_secret,
    )
    from shared.taxonomy import load_taxonomy

    out: Dict[str, Any] = {}
    work = Path(tempfile.mkdtemp(prefix="hermes-demo-safeguards-"))
    try:
        # -- 1. Baseline isolation: flood baseline ratings on a COPY, re-rank -------
        iso_db = work / "baseline_iso.db"
        shutil.copy(db_path, iso_db)
        iso = HermesService(db=HermesDB(iso_db))
        req = StaffingRequest(
            request_id="baseline-iso", requester_id=REQUESTER,
            required_skills={k: ProficiencyLevel(v) for k, v in REQUIRED_SKILLS.items()}, shortlist_size=10,
        )
        before = [(c.coded_identity, c.fitness_score) for c in iso.rank(req, min_coverage_ratio=0.0).candidates]
        flooded = 0
        for i, (ident, _) in enumerate(before):
            for skill in REQUIRED_SKILLS:
                iso.db.insert_baseline(
                    f"flood-{i}-{skill}", ident, skill, 5.0, 5 if i == len(before) - 1 else 1,
                    "AWS", "five_point_undefined", skill_id=skill,
                )
                flooded += 1
        req2 = req.model_copy(update={"request_id": "baseline-iso-2"})
        after = [(c.coded_identity, c.fitness_score) for c in iso.rank(req2, min_coverage_ratio=0.0).candidates]
        out["baseline_isolation"] = {
            "baseline_rows_injected": flooded,
            "ranking_unchanged": before == after,
            "note": "Manager ratings favouring the last-ranked candidate did not move any score.",
        }

        # -- 2-5. Live API controls against the demo database ------------------
        prior_db = os.environ.get("HERMES_DB_PATH")
        os.environ["HERMES_DB_PATH"] = str(db_path)
        api_main.reset_service_for_tests(None)
        try:
            with TestClient(api_main.app) as client:
                def tok(sub):
                    t = client.post("/api/auth/token", json={"sub": sub}).json()["access_token"]
                    return {"Authorization": f"Bearer {t}"}

                mgr, mgr2, emp = tok("demo-manager"), tok("demo-manager-2"), tok("demo-employee")
                body = {"request_id": "gov-demo", "required_skills": REQUIRED_SKILLS, "shortlist_size": 3,
                        "min_coverage_ratio": 0.5}
                ranked = client.post("/api/fitness/rank", headers=mgr, json=body).json()
                excluded = ranked.get("excluded_candidates", [])

                def status(method, path, headers=None, json_body=None):
                    return client.request(method, path, headers=headers, json=json_body).status_code

                out["invalid_input_rejection"] = {
                    name: status("POST", "/api/fitness/rank", mgr, {"request_id": "bad", **payload})
                    for name, payload in {
                        "unknown_skill": {"required_skills": {"not_a_skill": 3}},
                        "level_above_max": {"required_skills": {"container_orchestration": 6}},
                        "level_below_min": {"required_skills": {"container_orchestration": 0}},
                        "fractional_level": {"required_skills": {"container_orchestration": 3.5}},
                        "string_level": {"required_skills": {"container_orchestration": "3"}},
                        "empty_requirements": {"required_skills": {}},
                        "coverage_above_one": {"required_skills": {"container_orchestration": 3},
                                               "min_coverage_ratio": 1.5},
                    }.items()
                }
                out["identity_governance"] = {
                    "unauthenticated_rank": status("POST", "/api/fitness/rank", None, body),
                    "employee_rank": status("POST", "/api/fitness/rank", emp, {**body, "request_id": "emp-try"}),
                    "employee_list_identities": status("GET", "/api/identities", emp),
                    "employee_create_identity": status("POST", "/api/identity/abstract", emp,
                                                       {"employee_id": "SYN-X", "name": "Synthetic"}),
                    "other_manager_rank_same_request": status("POST", "/api/fitness/rank", mgr2, body),
                    "other_manager_resolve": status("POST", "/api/identity/resolve", mgr2, {"request_id": "gov-demo"}),
                    "other_manager_decision": status("POST", "/api/staffing/gov-demo/decision", mgr2,
                                                     {"status": "rejected"}),
                    "token_with_client_asserted_role": status("POST", "/api/auth/token", None,
                                                              {"sub": "demo-employee", "roles": ["admin"]}),
                    "owner_resolve": status("POST", "/api/identity/resolve", mgr, {"request_id": "gov-demo"}),
                }
                decision_on_excluded = None
                if excluded:
                    r = client.post("/api/staffing/gov-demo/decision", headers=mgr, json={
                        "status": "overridden", "chosen_coded_identity": excluded[0]["coded_identity"]})
                    decision_on_excluded = {"status": r.status_code, "error": r.json().get("error")}
                out["excluded_candidate"] = {
                    "excluded": excluded,
                    "decision_naming_excluded_candidate": decision_on_excluded,
                }
        finally:
            api_main.reset_service_for_tests(None)
            if prior_db is None:
                os.environ.pop("HERMES_DB_PATH", None)
            else:
                os.environ["HERMES_DB_PATH"] = prior_db

        # -- 6. Audit tamper detection on a COPY -------------------------------
        tamper_db = work / "tamper.db"
        shutil.copy(db_path, tamper_db)
        shutil.copy(HermesDB(db_path).anchor_path(), tamper_db.with_name(tamper_db.name + ".audit-anchor.json"))
        tampered = HermesDB(tamper_db)
        intact = tampered.verify_audit_chain() == []
        with tampered.session() as conn:
            conn.execute("DELETE FROM audit_ledger WHERE seq = (SELECT MAX(seq) FROM audit_ledger)")
        out["audit_integrity"] = {
            "untampered_chain_verifies": intact,
            "latest_event_deleted_detected": bool(tampered.verify_audit_chain()),
            "note": "Tamper-evident application audit chain with external integrity anchor (not WORM).",
        }

        # -- 7. Real-data safety (no real data is read) ------------------------
        refusals = {}
        prior_tm = os.environ.get("HERMES_TEST_MODE")
        os.environ["HERMES_TEST_MODE"] = "1"
        try:
            require_real_data_ingest_secret()
            refusals["real_ingest_in_test_mode"] = "ACCEPTED"
        except RuntimeError:
            refusals["real_ingest_in_test_mode"] = "REFUSED"
        finally:
            if prior_tm is None:
                os.environ.pop("HERMES_TEST_MODE", None)
            else:
                os.environ["HERMES_TEST_MODE"] = prior_tm
        try:
            validate_real_data_secret(sorted(PUBLISHED_SECRETS)[0])
            refusals["published_secret_without_test_flag"] = "ACCEPTED"
        except RuntimeError:
            refusals["published_secret_without_test_flag"] = "REFUSED"
        legacy = HermesDB(work / "legacy_untrusted.db")
        legacy.upsert_identity("EMP-00000001", "syn-legacy", display_name="Synthetic")
        refusals["database_without_trust_metadata"] = assess_database_trust(
            legacy, "demo-only-strong-secret-0123456789abcdef").reason
        resolver = SkillAliasResolver(HermesDB(work / "alias.db"), ontology_lookup_map(load_taxonomy()))
        pending = resolver.resolve("Unmapped Workbook Label")
        out["real_data_pipeline"] = {
            "stages": ["REAL DATA INGESTION", "QUALITY VALIDATION", "IDENTITY ABSTRACTION",
                       "ONTOLOGY MAPPING", "UNMAPPED LABELS", "NO UNSAFE SCORING"],
            "refusals": refusals,
            "unmapped_label_resolution": {"mapped_by": pending.mapped_by, "skill_id": pending.skill_id},
            "note": ("Real workbook labels stay pending until a human approves a mapping; pending labels "
                     "have no skill_id and cannot be scored. The scored population here is synthetic."),
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return out


def _comparable(transcript: Dict[str, Any]) -> str:
    """The transcript must already be free of wall-clock values."""
    return json.dumps(transcript, sort_keys=True, default=str)


def _safeguard_failures(sg: Dict[str, Any]) -> List[str]:
    """Assert the expected outcome of every safeguard; return human-readable failures."""
    failures: List[str] = []
    if not sg.get("baseline_isolation", {}).get("ranking_unchanged"):
        failures.append("baseline isolation")
    for name, code in sg.get("invalid_input_rejection", {}).items():
        if code != 422:
            failures.append(f"invalid input {name} -> {code}")
    expected = {
        "unauthenticated_rank": 401, "employee_rank": 403, "employee_list_identities": 403,
        "employee_create_identity": 403, "other_manager_rank_same_request": 403,
        "other_manager_resolve": 403, "other_manager_decision": 403,
        "token_with_client_asserted_role": 422, "owner_resolve": 200,
    }
    for name, code in expected.items():
        if sg.get("identity_governance", {}).get(name) != code:
            failures.append(f"governance {name} -> {sg.get('identity_governance', {}).get(name)}")
    exc = sg.get("excluded_candidate", {})
    if not exc.get("excluded") or (exc.get("decision_naming_excluded_candidate") or {}).get("status") != 422:
        failures.append("excluded candidate refusal")
    audit = sg.get("audit_integrity", {})
    if not (audit.get("untampered_chain_verifies") and audit.get("latest_event_deleted_detected")):
        failures.append("audit anchor")
    rd = sg.get("real_data_pipeline", {})
    refusals = rd.get("refusals", {})
    if refusals.get("real_ingest_in_test_mode") != "REFUSED" or refusals.get("published_secret_without_test_flag") != "REFUSED":
        failures.append("real-data secret refusal")
    if refusals.get("database_without_trust_metadata") != "missing_trust_metadata":
        failures.append("untrusted database refusal")
    if rd.get("unmapped_label_resolution", {}).get("skill_id") is not None:
        failures.append("pending label became a skill")
    return failures


def verify() -> int:
    """Run twice into separate databases; assert identical transcripts."""
    with tempfile.TemporaryDirectory() as tmp:
        a = run(Path(tmp) / "a.db")
        b = run(Path(tmp) / "b.db")
    if _comparable(a) == _comparable(b):
        print("DETERMINISM OK - two independent runs produced identical transcripts")
        print(f"  scoring_config_version: {a['scoring_config_version']}")
        print(f"  computation_run_id:     {a['computation_run_id']}")
        failed = _safeguard_failures(a.get("safeguards", {}))
        if failed:
            print("SAFEGUARD CHECK FAILED:", "; ".join(failed), file=sys.stderr)
            return 1
        print("SAFEGUARDS OK   - baseline isolation, input rejection, identity governance,")
        print("                  excluded-candidate refusal, audit anchor, real-data refusal")
        return 0
    print("DETERMINISM FAILED - transcripts differ", file=sys.stderr)
    for step_a, step_b in zip(a["steps"], b["steps"]):
        if json.dumps(step_a, sort_keys=True, default=str) != json.dumps(
            step_b, sort_keys=True, default=str
        ):
            print(f"  first divergence at step {step_a['step']}: {step_a['title']}", file=sys.stderr)
            break
    return 1


def _print_human(transcript: Dict[str, Any]) -> None:
    print("=" * 78)
    print("HERMES - SVP DEMONSTRATION       data: SYNTHETIC (pilot fixture E1001-E1005)")
    print(
        f"as_of={transcript['as_of']}  run={transcript['computation_run_id']}  "
        f"config={transcript['scoring_config_version']}"
    )
    print("=" * 78)
    for s in transcript["steps"]:
        print(f"\n[{s['step']:>2}] {s['title']}")
        print("-" * 78)
        print(json.dumps(s["detail"], indent=2, default=str))
    print("\n" + "=" * 78)
    print("SAFEGUARDS (live checks; status codes / reason codes only)")
    print("=" * 78)
    print(json.dumps(transcript.get("safeguards", {}), indent=2, default=str))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic Hermes SVP demo")
    parser.add_argument("--db", type=Path, default=None, help="keep the demo DB here (default: temp dir, removed)")
    parser.add_argument("--json", action="store_true", help="emit JSON only")
    parser.add_argument("--verify", action="store_true", help="prove reproducibility")
    parser.add_argument("--out", type=Path, default=None, help="also write the transcript JSON here")
    args = parser.parse_args(argv)

    os.environ.setdefault("HERMES_TEST_MODE", "1")

    if args.verify:
        return verify()

    if args.db is None:
        with tempfile.TemporaryDirectory(prefix="hermes-demo-") as tmp:
            transcript = run(Path(tmp) / "demo.db")
    else:
        transcript = run(args.db)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(transcript, indent=2, default=str), encoding="utf-8")

    if args.json:
        print(json.dumps(transcript, indent=2, default=str))
    else:
        _print_human(transcript)
        if args.out is not None:
            print(f"\nTranscript written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
