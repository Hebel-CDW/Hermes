"""Production Teams provider — NOT IMPLEMENTED.

This is deliberately a stub, not a best-effort guess at the Microsoft Graph /
Bot Framework calls, because untested integration code presented as "the
production provider" is its own form of fake production-readiness — exactly
what this project has been told not to do. Every method raises
NotImplementedError naming exactly what real-world setup is missing.

To implement this for real, in order:

1. Register an Azure AD app with Bot Framework / Microsoft Teams channel
   permissions (Teams admin consent required for an org-wide capability bot).
2. Register the bot with the Bot Framework and enable the Teams channel.
3. Expose a public HTTPS webhook endpoint for incoming Teams Activities
   (the employee's submitted card) — this becomes a new API route, not
   something this provider can originate on its own.
4. Use the Bot Framework SDK (or raw Bot Connector REST API) to POST an
   Activity containing the Adaptive Card from integrations.teams.cards to
   the employee's 1:1 conversation with the bot.
5. Parse the incoming Activity's ``value`` (the submitted card data) in the
   webhook route, validate it against integrations.teams.models.AssessmentResponse
   (unchanged — the mock and real providers share the exact same response
   schema and the exact same integrations.teams.service pipeline downstream).

None of the above has been built or tested here — there is no Teams tenant,
Bot Framework registration, or webhook endpoint in this environment to test
against. OIDC auth (shared/oidc_auth.py) proves the *pattern* this project
uses for "validated against a real protocol without a live tenant" is
achievable; Teams additionally needs an inbound webhook, which can't be
exercised at all without a real, internet-reachable deployment.
"""

from __future__ import annotations

from integrations.teams.models import AssessmentInvite

_NOT_IMPLEMENTED = (
    "MicrosoftTeamsProvider is not implemented. See this module's docstring "
    "for the exact Bot Framework/Graph setup required before it can be."
)


class MicrosoftTeamsProvider:
    is_mock = False

    def __init__(self, *_, **__) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def send_card(self, coded_identity: str, card: dict) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def send_assessment(self, invite: AssessmentInvite) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def send_profile_update(self, coded_identity: str, skill_label: str) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def send_notification(self, coded_identity: str, message: str) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED)
