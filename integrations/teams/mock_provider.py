"""Development-only Teams provider. Fully functional in-memory simulation —
not a stub — so the real send -> answer -> DECLARED-evidence pipeline can be
exercised end-to-end without a Teams tenant. Clearly labeled: ``is_mock`` is
always True, and the production smoke test checks this before claiming any
Teams configuration is real (Phase 12).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from integrations.teams.cards import build_capability_check_card
from integrations.teams.models import AssessmentInvite


class MockTeamsProvider:
    is_mock = True

    def __init__(self) -> None:
        self.sent_cards: Dict[str, Dict[str, Any]] = {}
        self.sent_assessments: Dict[str, AssessmentInvite] = {}
        self.notifications: List[Dict[str, str]] = []

    def send_card(self, coded_identity: str, card: dict) -> str:
        message_id = str(uuid.uuid4())
        self.sent_cards[message_id] = {"coded_identity": coded_identity, "card": card}
        return message_id

    def send_assessment(self, invite: AssessmentInvite) -> str:
        assessment_id = str(uuid.uuid4())
        card = build_capability_check_card(invite)
        self.send_card(invite.coded_identity, card)
        self.sent_assessments[assessment_id] = invite
        return assessment_id

    def send_profile_update(self, coded_identity: str, skill_label: str) -> str:
        return self.send_notification(
            coded_identity, f"Hermes noticed recent work involving {skill_label}. Update your profile?"
        )

    def send_notification(self, coded_identity: str, message: str) -> str:
        message_id = str(uuid.uuid4())
        self.notifications.append({"id": message_id, "coded_identity": coded_identity, "message": message})
        return message_id
