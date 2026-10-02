"""Builds real Adaptive Card JSON (schema version 1.5, adaptivecards.io) for a
capability check. This is a static, well-defined public schema — the card
structure itself can be built and validated correctly without a live Teams
tenant; what *cannot* be verified without one is actual delivery/rendering
inside a real Teams client (see microsoft_provider.py).
"""

from __future__ import annotations

from typing import Any, Dict

from integrations.teams.models import AssessmentInvite

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.5"

_EXPERIENCE_CHOICES = [
    {"title": "Beginner", "value": "beginner"},
    {"title": "Working", "value": "working"},
    {"title": "Advanced", "value": "advanced"},
    {"title": "Expert", "value": "expert"},
]
_RECENCY_CHOICES = [
    {"title": "Under 30 days", "value": "under_30_days"},
    {"title": "1–6 months", "value": "1_to_6_months"},
    {"title": "6–12 months", "value": "6_to_12_months"},
    {"title": "1+ year", "value": "over_1_year"},
]


def build_capability_check_card(invite: AssessmentInvite) -> Dict[str, Any]:
    body = [
        {"type": "TextBlock", "text": "Hermes capability check", "weight": "bolder", "size": "medium"},
        {"type": "TextBlock", "text": "Help us understand what you can actually do.", "wrap": True},
    ]
    for q in invite.questions:
        body.extend([
            {"type": "TextBlock", "text": q.skill_label, "weight": "bolder", "spacing": "medium"},
            {"type": "Input.Toggle", "id": f"{q.skill_id}__actively_used", "title": "I actively work with this"},
            {
                "type": "Input.ChoiceSet", "id": f"{q.skill_id}__experience", "style": "compact",
                "placeholder": "Experience level", "choices": _EXPERIENCE_CHOICES,
            },
            {
                "type": "Input.ChoiceSet", "id": f"{q.skill_id}__recency", "style": "compact",
                "placeholder": "How recently used", "choices": _RECENCY_CHOICES,
            },
            {"type": "Input.Toggle", "id": f"{q.skill_id}__delivered", "title": "Delivered this in real work"},
        ])
    return {
        "$schema": ADAPTIVE_CARD_SCHEMA,
        "type": "AdaptiveCard",
        "version": ADAPTIVE_CARD_VERSION,
        "body": body,
        "actions": [{"type": "Action.Submit", "title": "Submit", "data": {"coded_identity": invite.coded_identity}}],
    }
