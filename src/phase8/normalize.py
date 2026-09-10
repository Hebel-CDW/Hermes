"""Single place for baseline scale normalisation (revisable without re-ingest of raw values)."""

from __future__ import annotations

from typing import Optional, Tuple


def normalize_level(raw_value: Optional[float], source_scale: str) -> Optional[int]:
    """Map raw workbook values to Hermes 1..5, or NULL.

    D1: raw_value 0.0 => normalised_level NULL (NOT ASSESSED), never level 0/1.
    """
    if raw_value is None:
        return None
    try:
        v = float(raw_value)
    except (TypeError, ValueError):
        return None
    if v == 0.0:
        return None
    if source_scale == "collab_four_point":
        # Collab 1..4 → stretch to 1..5: 1→1, 2→2, 3→4, 4→5
        mapping = {1.0: 1, 2.0: 2, 3.0: 4, 4.0: 5}
        if v in mapping:
            return mapping[v]
        # non-integer already filtered before call; defensive
        nearest = min(mapping.keys(), key=lambda x: abs(x - v))
        return mapping[nearest]
    # five_point_undefined: 1..5 pass through when integer-like
    if 1.0 <= v <= 5.0:
        return int(round(v))
    return None


def classify_scale(sheet_name: str) -> str:
    return "collab_four_point" if sheet_name == "Collab" else "five_point_undefined"
