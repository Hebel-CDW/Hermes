"""Confirm schema and models contain no protected-attribute fields."""

from __future__ import annotations

import re
from pathlib import Path

from shared.models import PROTECTED_ATTRIBUTE_FIELDS


def scan_sql(path: Path):
    text = path.read_text(encoding="utf-8").lower()
    hits = []
    for field in PROTECTED_ATTRIBUTE_FIELDS:
        if re.search(r"\b" + re.escape(field) + r"\b", text):
            hits.append(f"{path.name}:{field}")
    return hits


def main() -> int:
    paths = [
        Path("infra/sqlite/001_schema.sql"),
        Path("infra/sql/001_schema.sql"),
    ]
    hits = []
    found_any = False
    for path in paths:
        if path.exists():
            found_any = True
            hits.extend(scan_sql(path))
    if not found_any:
        hits.append("missing_schema")
    if not PROTECTED_ATTRIBUTE_FIELDS:
        hits.append("missing_protected_attribute_blocklist")
    status = "pass" if not hits else "fail"
    print({"status": status, "forbidden_field_hits": hits})
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
