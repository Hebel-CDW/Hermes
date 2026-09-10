"""Demand signal interface — stub for requisitions / ticket volume pipelines."""

from __future__ import annotations

from typing import Dict, Mapping, Optional, Protocol


class DemandSignalSource(Protocol):
    def load_weights(self) -> Mapping[str, float]:
        ...


class FixtureDemandSource:
    def __init__(self, weights: Optional[Mapping[str, float]] = None) -> None:
        self._weights = dict(weights or {})

    def load_weights(self) -> Dict[str, float]:
        return dict(self._weights)


class TicketVolumeDemandSource:
    """Placeholder: convert skill ticket counts into 0..1 demand weights."""

    def __init__(self, counts: Mapping[str, int]) -> None:
        self._counts = dict(counts)

    def load_weights(self) -> Dict[str, float]:
        if not self._counts:
            return {}
        peak = max(self._counts.values()) or 1
        return {k: round(v / peak, 4) for k, v in self._counts.items()}
