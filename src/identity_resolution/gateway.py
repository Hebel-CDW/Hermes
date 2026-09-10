"""Governed identity resolution for shortlisted candidates only."""

from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence, Set

from identity_abstraction.gate import IdentityAbstractionGate
from shared.audit import AuditLedger
from shared.models import RankedCandidate


class ResolutionDenied(Exception):
    """Raised when resolution violates gateway policy."""


class IdentityResolutionGateway:
    def __init__(self, gate: IdentityAbstractionGate, audit: Optional[AuditLedger] = None) -> None:
        self._gate = gate
        self._audit = audit or AuditLedger()

    def resolve_shortlist(
        self,
        request_id: str,
        requester_id: str,
        shortlist: Sequence[RankedCandidate],
        allowed_requester_id: str,
    ) -> List[Dict[str, str]]:
        if requester_id != allowed_requester_id:
            raise ResolutionDenied("requester is not authorized for this staffing request")

        allowed: Set[str] = {c.coded_identity for c in shortlist}
        resolved: List[Dict[str, str]] = []
        for candidate in shortlist:
            raw = self._gate.resolve_for_gateway(candidate.coded_identity)
            if raw is None:
                raise ResolutionDenied(f"unknown coded identity: {candidate.coded_identity}")
            if candidate.coded_identity not in allowed:
                raise ResolutionDenied("attempt to resolve non-shortlisted identity")
            resolved.append(
                {
                    "coded_identity": candidate.coded_identity,
                    "display_name": raw,
                    "rank": str(candidate.rank),
                    "fitness_score": str(candidate.fitness_score),
                }
            )

        self._audit.append(
            "identity_resolution",
            actor=requester_id,
            payload={
                "request_id": request_id,
                "resolved_tokens": [r["coded_identity"] for r in resolved],
                "count": len(resolved),
            },
        )
        return resolved

    def resolve_one(
        self,
        request_id: str,
        requester_id: str,
        coded_identity: str,
        shortlist_tokens: Sequence[str],
        allowed_requester_id: str,
    ) -> Mapping[str, str]:
        if requester_id != allowed_requester_id:
            raise ResolutionDenied("requester is not authorized for this staffing request")
        if coded_identity not in set(shortlist_tokens):
            raise ResolutionDenied("coded identity is not on the shortlist")
        raw = self._gate.resolve_for_gateway(coded_identity)
        if raw is None:
            raise ResolutionDenied(f"unknown coded identity: {coded_identity}")
        self._audit.append(
            "identity_resolution",
            actor=requester_id,
            payload={
                "request_id": request_id,
                "resolved_tokens": [coded_identity],
                "count": 1,
            },
        )
        return {"coded_identity": coded_identity, "display_name": raw}
