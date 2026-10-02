"""The Teams provider interface. Mirrors src/ai/provider.py's discipline:
minimal surface, no business logic here — card content, DECLARED-evidence
creation and governance live in integrations/teams/{cards,service}.py.
"""

from __future__ import annotations

from typing import Protocol

from integrations.teams.models import AssessmentInvite


class TeamsUnavailableError(Exception):
    """Raised by any provider when it cannot deliver. Callers must fail
    safely — Hermes's core manager workflow never depends on Teams."""


class TeamsProvider(Protocol):
    def send_card(self, coded_identity: str, card: dict) -> str:
        """Send an arbitrary Adaptive Card. Returns a provider-side message id."""
        ...

    def send_assessment(self, invite: AssessmentInvite) -> str:
        """Send a capability-check card built from ``invite``. Returns an
        assessment id the caller can later look up a response against."""
        ...

    def send_profile_update(self, coded_identity: str, skill_label: str) -> str:
        """'Hermes noticed recent work involving X — update your profile?'"""
        ...

    def send_notification(self, coded_identity: str, message: str) -> str:
        """Plain text notification (e.g. assessment confirmation)."""
        ...
