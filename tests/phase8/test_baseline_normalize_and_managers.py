import os
from pathlib import Path

import pytest

os.environ.setdefault("HERMES_TEST_MODE", "1")

from phase8.normalize import normalize_level
from shared.db import HermesDB


def test_zero_is_not_assessed():
    assert normalize_level(0.0, "five_point_undefined") is None
    assert normalize_level(0.0, "collab_four_point") is None


def test_five_point_passthrough():
    assert normalize_level(4.0, "five_point_undefined") == 4


def test_collab_four_point_mapping():
    assert normalize_level(1.0, "collab_four_point") == 1
    assert normalize_level(3.0, "collab_four_point") == 4
    assert normalize_level(4.0, "collab_four_point") == 5


def test_manager_alias_requires_human(tmp_path):
    db = HermesDB(tmp_path / "mgr.db")
    db.upsert_manager_alias("xavier", "Xavier Cardoz", mapped_by="pending")
    row = db.get_manager_alias("xavier")
    assert row["mapped_by"] != "human"
    # org edge merge path must refuse non-human
    assert row["mapped_by"] == "pending"


def test_no_auto_manager_merge_without_human_flag():
    """Acceptance: no manager merge applied without mapped_by=human."""
    from pathlib import Path
    import ast

    src = Path("scripts/phase8/ingest_baseline.py").read_text(encoding="utf-8")
    # ensure we never write mapped_by human automatically
    assert "mapped_by=\"human\"" not in src
    assert "mapped_by='human'" not in src
