"""Phase 9 — the SVP demo must be byte-reproducible.

A demo whose numbers move between runs cannot be interrogated. These tests pin the
determinism contract: same fixture + same pinned clock + same run id => identical
transcript, and the transcript must never contain a real name before the governed
resolution step.
"""

from __future__ import annotations

import json
import os

os.environ.setdefault("HERMES_TEST_MODE", "1")
os.environ.setdefault("IDENTITY_MAP_SECRET", "hermes-test-mode-secret-not-for-prod")
os.environ.setdefault("HERMES_JWT_SECRET", "hermes-test-jwt-secret-32chars!!")

from scripts.demo_svp import AS_OF, REQUIRED_SKILLS, RUN_ID, run  # noqa: E402


def _canonical(transcript) -> str:
    return json.dumps(transcript, sort_keys=True, default=str)


def test_two_runs_produce_identical_transcripts(tmp_path):
    a = run(tmp_path / "a.db")
    b = run(tmp_path / "b.db")
    assert _canonical(a) == _canonical(b), "demo transcript is not reproducible"


def test_transcript_pins_its_reproducibility_keys(tmp_path):
    t = run(tmp_path / "keys.db")
    assert t["as_of"] == AS_OF.isoformat()
    assert t["computation_run_id"] == RUN_ID
    assert t["scoring_config_version"]
    assert t["data_classification"] == "SYNTHETIC"


def test_all_fourteen_steps_are_present_and_ordered(tmp_path):
    t = run(tmp_path / "steps.db")
    numbers = [s["step"] for s in t["steps"]]
    assert numbers == list(range(1, 15))
    assert all(s["title"] for s in t["steps"])


def test_ranking_step_is_evidence_grounded(tmp_path):
    t = run(tmp_path / "rank.db")
    ranking = next(s for s in t["steps"] if s["step"] == 5)
    assert ranking["detail"]["shortlist"], "demo must produce a shortlist"
    # Exclusions carry machine-readable reasons.
    for excluded in ranking["detail"]["excluded_candidates"]:
        assert excluded["reason"]


def test_inspector_step_lets_a_reviewer_recompute_the_score(tmp_path):
    """The headline claim: 'why did this candidate score X?' answerable from the payload."""
    t = run(tmp_path / "inspect.db")
    inspector = next(s for s in t["steps"] if s["step"] == 6)
    calc = inspector["detail"]["calculation"]
    per_skill = inspector["detail"]["per_skill"]

    contributions = []
    for detail in per_skill.values():
        if detail["status"] == "missing":
            contributions.append(0.0)
            continue
        contributions.append(
            detail["level_ratio"]
            * detail["confidence"]
            * detail["volume_score"]
            * detail["freshness"]
            * detail["adjacency_discount"]
        )
    mean = sum(contributions) / len(contributions)
    multiplier = (1 - calc["allocation_weight"]) + calc["allocation_weight"] * calc["allocation"]
    assert round(mean * multiplier, 4) == calc["fitness_score"]


def test_identity_stays_coded_until_the_resolution_step(tmp_path):
    t = run(tmp_path / "coded.db")
    pre_resolution = [s for s in t["steps"] if s["step"] < 9]
    blob = json.dumps(pre_resolution, default=str)
    assert "Alex Rivera" not in blob, "display name leaked before the resolution step"
    # No step before 9 should expose anything from identity_vault.
    assert "display_name" not in blob


def test_resolution_step_is_the_only_place_names_appear(tmp_path):
    t = run(tmp_path / "resolve.db")
    resolution = next(s for s in t["steps"] if s["step"] == 9)
    assert resolution["detail"]["resolved_count"] >= 1
    assert all(r["display_name"] for r in resolution["detail"]["resolved"])


def test_decision_is_recorded_and_flagged_as_audit_only(tmp_path):
    t = run(tmp_path / "decide.db")
    decision = next(s for s in t["steps"] if s["step"] == 10)
    assert decision["detail"]["status"] == "accepted"
    assert decision["detail"]["engine_rank_of_choice"] == 1
    assert "never read back into scoring" in decision["detail"]["note"]


def test_audit_chain_verifies_within_the_demo(tmp_path):
    t = run(tmp_path / "audit.db")
    audit = next(s for s in t["steps"] if s["step"] == 11)
    assert audit["detail"]["chain_verified"] is True
    assert audit["detail"]["chain_errors"] == []
    assert audit["detail"]["ledger_events"] > 0


def test_recalculation_is_stable_across_pinned_runs(tmp_path):
    t = run(tmp_path / "recalc.db")
    history = next(s for s in t["steps"] if s["step"] == 14)
    assert history["detail"]["pinned_runs"] == ["demo-run-0001", "demo-run-0002"]
    assert history["detail"]["recalculation_is_stable"] is True


def test_demo_required_skills_are_canonical_ontology_ids():
    from shared.taxonomy import load_taxonomy

    ids = {s.skill_id for s in load_taxonomy().all_skills()}
    assert set(REQUIRED_SKILLS) <= ids
