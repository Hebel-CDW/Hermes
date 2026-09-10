import pytest

from scripts.narrate import assert_grounded_staffing


def test_rejects_ungrounded_candidate():
    with pytest.raises(AssertionError):
        assert_grounded_staffing(
            {"candidates": [{"coded_identity": "EMP-1", "evidence_ids": [], "per_skill_reasoning": {}}]}
        )
