"""Typed domain errors with a stable machine-readable code and HTTP status.

The API maps every ``HermesError`` to ``{"detail": <message>, "error": <code>}``
with ``http_status``. ``detail`` is kept for compatibility with the frontend.
"""

from __future__ import annotations


class HermesError(Exception):
    code = "hermes_error"
    http_status = 400

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        if code:
            self.code = code


class RequestNotFound(HermesError):
    code = "request_not_found"
    http_status = 404


class RequestOwnershipError(HermesError):
    """The authenticated principal does not own the staffing request."""

    code = "request_not_owned"
    http_status = 403


class RequestStateConflict(HermesError):
    code = "request_state_conflict"
    http_status = 409


class DecisionValidationError(HermesError):
    code = "invalid_decision"
    http_status = 422


class UnknownSkillError(HermesError, ValueError):
    """A skill id that is not in the governed ontology."""

    code = "unknown_skill"
    http_status = 422


class ConfigurationError(HermesError, ValueError):
    code = "invalid_configuration"
    http_status = 500


class UntrustedDatabaseError(HermesError, RuntimeError):
    """The database lacks trust metadata or holds reversible identity mappings."""

    code = "untrusted_database"
    http_status = 503


class AuthorizationError(HermesError):
    code = "forbidden"
    http_status = 403


class AuthenticationError(HermesError, PermissionError):
    code = "unauthenticated"
    http_status = 401


class WorkbookFrozenError(HermesError, RuntimeError):
    """A Skill Matrix workbook after the frozen 2025 survey must not be ingested."""

    code = "workbook_frozen"
    http_status = 409
