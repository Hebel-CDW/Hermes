"""Phase 5 — the real-data activation status must be a hard, count-derived gate.

``skills_matrix`` row count (``scored_people``) is the only thing that can move the
state past GOVERNANCE_PENDING/INGESTED. No amount of staged, unmapped, or undated
data may ever report ACTIVE or VALIDATED.
"""

from __future__ import annotations

import os

os.environ.setdefault("HERMES_TEST_MODE", "1")

from shared.read_models import _activation_status  # noqa: E402


def _counts(**overrides):
    base = {
        "people_imported": 10,
        "pending_aliases": 0,
        "certificates_staged": 0,
        "certificates_promoted": 0,
        "scored_people": 0,
    }
    base.update(overrides)
    return base


def test_no_ingest_run_is_not_ready():
    status = _activation_status(_counts(), run=None)
    assert status["state"] == "NOT_READY"
    assert status["scored_people"] == 0


def test_ingested_with_no_blockers_and_zero_scored():
    status = _activation_status(_counts(), run={"run_id": "r1"})
    assert status["state"] == "INGESTED"
    assert status["scored_people"] == 0


def test_pending_aliases_block_at_zero_scored():
    status = _activation_status(_counts(pending_aliases=673), run={"run_id": "r1"})
    assert status["state"] == "GOVERNANCE_PENDING"
    assert "673" in status["reason"]


def test_unpromoted_certs_block_at_zero_scored():
    status = _activation_status(
        _counts(certificates_staged=427, certificates_promoted=0), run={"run_id": "r1"}
    )
    assert status["state"] == "GOVERNANCE_PENDING"
    assert "427" in status["reason"]


def test_scored_with_remaining_blockers_is_partially_active():
    status = _activation_status(
        _counts(scored_people=3, pending_aliases=50, certificates_staged=427, certificates_promoted=5),
        run={"run_id": "r1"},
    )
    assert status["state"] == "PARTIALLY_ACTIVE"
    assert status["scored_people"] == 3


def test_scored_with_no_blockers_is_active():
    status = _activation_status(
        _counts(scored_people=10, certificates_staged=427, certificates_promoted=427),
        run={"run_id": "r1"},
    )
    assert status["state"] == "ACTIVE"
    assert status["scored_people"] == 10


def test_zero_scored_is_never_active_or_validated_regardless_of_other_counts():
    """The explicit hard-gate property: scored_people==0 can never produce ACTIVE/VALIDATED."""
    for pending in (0, 1, 1000):
        for promoted in (0, 1, 427):
            status = _activation_status(
                _counts(
                    scored_people=0,
                    pending_aliases=pending,
                    certificates_staged=427,
                    certificates_promoted=promoted,
                ),
                run={"run_id": "r1"},
            )
            assert status["state"] in {"INGESTED", "GOVERNANCE_PENDING"}
