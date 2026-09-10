"""Org relationship checks for gap subject binding."""

from __future__ import annotations

from typing import TYPE_CHECKING

from shared.auth import AuthPrincipal

if TYPE_CHECKING:
    from shared.db import HermesDB


class SubjectAccessDenied(PermissionError):
    pass


def can_view_gaps(principal: AuthPrincipal, subject_coded_id: str, db: "HermesDB") -> bool:
    if principal.is_admin:
        return True
    if principal.coded_identity and principal.coded_identity == subject_coded_id:
        return True
    if principal.is_manager and principal.coded_identity:
        return db.is_direct_report(principal.coded_identity, subject_coded_id)
    return False


def require_gap_access(principal: AuthPrincipal, subject_coded_id: str, db: "HermesDB") -> None:
    if not can_view_gaps(principal, subject_coded_id, db):
        raise SubjectAccessDenied("not authorized to view gaps for this coded identity")
