# Human oversight evidence

Managers must explicitly record a staffing decision:

```http
POST /api/staffing/{request_id}/decision
Authorization: Bearer <jwt>
{ "status": "accepted|rejected|overridden", "chosen_coded_identity": "EMP-...", "override_note": "..." }
```

- Choosing rank ≠ 1 requires `overridden` + `override_note` in UI guidance.
- Events land in the integrity-chained audit ledger with `guardrail: never_score_on_historical_staffing_decisions`.
- Gaps ACL and resolve ownership enforce least privilege.
