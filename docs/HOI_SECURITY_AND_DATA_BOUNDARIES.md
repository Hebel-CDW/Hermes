# HOI — Security and data boundaries

## Roles
| Role | Can | Cannot |
|---|---|---|
| sales | create opportunity, upload, correct/approve requirements, market ranges, approved revenue total, export approved report | candidates, shortlists, any cost/margin, loaded cost |
| manager (delivery) | match, view coded shortlist, build/compare scenarios, Delivery approval, name reveal via gateway | loaded cost, per-person pay, cost components (sees revenue + margin band) |
| finance | policies, rate cards, loaded costs (the only reader), market import, Finance approval, full economics | match, name reveal |
| hr | view approvals/finance access log, HR authorization when individual pay was used | loaded cost values |
| admin | read deal data and audit | loaded cost values, edits |
Access also needs **deal-team membership** (owner adds members). Non-members get 404 (existence not disclosed).

## Boundaries (each has a test in `tests/api/test_hoi_api.py`)
1. Compensation never enters fitness: the ranking is identical before/after changing pay.
2. Loaded costs: Fernet-encrypted at rest (separate key), read only by Finance (access logged: actor+action, no values), consumed internally by the cost engine. Scenario results (per-person cost, totals, margin) are encrypted with the same key (`commercial_scenarios.result_json`, `cogs`, `profit`, `margin_pct`). Not in generic APIs, audit trail, platform ledger, logs or a full DB dump (tested). The audit writer *rejects* monetary key names structurally.
3. Documents: validated, checksummed, versioned, encrypted at rest (0600 files), storage URI never returned, filename sanitised, DOCX parsed by regex (no XML entity expansion).
4. Unapproved requirements cannot be matched, costed or analysed (409).
5. No automatic assignment: scenarios are drafts; approval records a decision only; availability/allocation tables untouched (tested).
6. Names: only through the existing identity-resolution gateway.
7. External LLM: none. The optional assist uses the configured local provider, receives document text only (no employee or payroll data), and its output is rejected unless quotes verify in the source.
8. Reports are role-redacted, omit per-line pay, list market provenance and carry a synthetic-data notice.

## Key management (read this before any deployment)
* `HOI_DOC_KEY` and `HOI_FINANCE_KEY` are two independent Fernet keys, so a document key can never open finance data (tested).
* **Outside local/test mode both are mandatory**; if either is missing the service refuses to start the corresponding operation (`ConfigurationError`), and a malformed key is never echoed back (tested).
* **In local/test mode a fallback key is derived from a constant that is published in this repository.** That is obfuscation for demo data, **not encryption in any security sense**. Never place real documents or real compensation data in a database that is running on the fallback key. Production needs keys from a secret manager/KMS with rotation; there is no rotation or re-encryption tooling yet.
* Fernet gives confidentiality and tamper detection per value; it does not stop a database administrator who also holds the application key.

## Resource limits and input handling
* Request bodies are bounded from the `Content-Length` header before they are read (documents 15 MB, benchmark import 2.1 MB, other HOI writes 3 MB); a write without `Content-Length` is refused (411). Uploaded files are capped at 10 MB.
* PDF streams are inflated with hard ceilings (20 MB per stream, 40 MB per file): a few-KB "zip bomb" PDF is rejected, not expanded. Extracted text above 2,000,000 characters is refused. Extraction keeps at most 50 roles and 60 skills per role so a draft always stays editable and approvable.
* The schema itself rejects invalid statuses, roles, bases, units, currencies and scopes (`CHECK` constraints, tested at the database).

## Access scoping
Every `/api/opportunities/{oid}/…` route is enumerated by a test and must answer 403/404 without leaking anything to six different non-members; a new route is picked up automatically. Admin/auditor can read a deal but not write to it.

## Design decisions to review (not defects)
* **No maker-checker rule:** the person who creates a scenario may also give the approval for their own lane (a manager creates and gives Delivery approval; Finance creates and gives Finance approval). Delivery, Finance and (where individual pay is used) HR remain three different people, but no rule stops one person preparing and approving within a lane.
* **Staffing requests created by matching:** each internal match stores a normal Hermes staffing request (required by the identity-resolution gateway). These appear as "open" in Requests and in the Overview's open-request count, and could in principle be decided through the existing requests flow; that records a Hermes decision only, it never writes to an HR system.
* **Audit integrity is tamper-evident, not tamper-proof:** the per-opportunity hash chain detects edits, but nothing external anchors it, so someone with full database write access could rewrite the whole chain consistently.
* The optional model assist sends document text to whichever provider is configured (local Ollama by default). Pointing it at a remote provider would send customer content off the machine; do not do that without a data-processing agreement.

## Known gaps (not solved here)
* Malware scanning and DLP: adapter only, files stored `not_scanned`.
* Encryption keys come from env vars; production needs Key Vault/KMS, rotation, and HR/Legal review of any real compensation data (design doc §2).
* Demo identity registry only; Entra ID/OIDC mapping of `sales/finance/hr` roles is untested against a real IdP.
* Extraction accuracy is unmeasured (no labelled corpus); confidence is heuristic. Fairness/adverse-impact review pending with governance reviewers.
* Rate limiting is per principal (120/min); no per-opportunity quotas.
