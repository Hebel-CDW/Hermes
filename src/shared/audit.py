"""Append-only audit ledger with optional SQLite persistence."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from shared.models import AuditEvent, utc_now

if TYPE_CHECKING:
    from shared.db import HermesDB


class AuditLedger:
    """Immutable append-only store of audit events (memory + optional SQLite)."""

    def __init__(self, db: Optional["HermesDB"] = None) -> None:
        self._events: List[AuditEvent] = []
        self._db = db

    def append(self, event_type: str, actor: str, payload: Dict[str, Any]) -> AuditEvent:
        event = AuditEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            actor=actor,
            payload=dict(payload),
            created_at=utc_now(),
        )
        self._events.append(event)
        if self._db is not None:
            self._db.append_audit(event.event_id, event.event_type, event.actor, event.payload)
        return event

    def all_events(self) -> List[AuditEvent]:
        return list(self._events)

    def by_type(self, event_type: str) -> List[AuditEvent]:
        return [e for e in self._events if e.event_type == event_type]
