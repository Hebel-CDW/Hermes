from pathlib import Path

from scripts.fairness_audit import scan_sql
from shared.models import PROTECTED_ATTRIBUTE_FIELDS


def test_sqlite_schema_has_no_protected_fields():
    hits = scan_sql(Path("infra/sqlite/001_schema.sql"))
    assert hits == []


def test_legacy_azure_schema_has_no_protected_fields():
    path = Path("infra/sql/001_schema.sql")
    if path.exists():
        assert scan_sql(path) == []


def test_protected_blocklist_configured():
    assert "gender" in PROTECTED_ATTRIBUTE_FIELDS
    assert "ethnicity" in PROTECTED_ATTRIBUTE_FIELDS
