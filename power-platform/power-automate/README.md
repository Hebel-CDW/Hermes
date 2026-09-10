# Power Automate flows (Hermes)

Flows move data only. They never score or resolve identity.

## Flows

| Flow | Source | Target |
|------|--------|--------|
| `sync-servicenow-tickets` | ServiceNow resolved incidents | `POST /api/identity/abstract` then staging |
| `sync-lms-certifications` | LMS certification completions | identity abstract endpoint |
| `sync-hr-role-history` | HR role/project assignments | identity abstract endpoint |
| `sync-declared-skills` | Manager-confirmed declared skills form | identity abstract endpoint |

## Retry / dead-letter

- Retry policy: exponential, 4 attempts
- Failed payloads land in `hermes-ingestion-dlq` (Storage queue)
- Alert Action Group on DLQ depth > 0

## Required fields

See [docs/runbooks/source-connectors.md](../../docs/runbooks/source-connectors.md).

Export solution package here when available: `HermesIngestion_*.zip`.
