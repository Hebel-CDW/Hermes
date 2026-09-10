# Future Azure path

The local-first MVP does not require Azure. The following remain in-repo as stubs for a later CDW tenancy:

- `infra/main.bicep` — Function App, Azure SQL, Key Vault, App Insights
- `infra/sql/001_schema.sql` — Azure SQL dialect of the matrix schema
- `power-platform/` — Power Automate / Copilot Studio / Power BI stubs
- `functions/` — legacy Azure Functions host (superseded by `api/`)

When Azure becomes available, map:

| Local | Azure |
|-------|-------|
| FastAPI | Azure Functions or Container Apps |
| SQLite | Azure SQL |
| Fixture ingest CLI | Power Automate connectors |
| hermes_query CLI | Copilot Studio (narrate-only) |
| dashboard HTML | Power BI |
