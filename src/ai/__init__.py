"""LLM-assist layer. Strict boundary: this package may only ASSIST — it never
computes a score, ranks a candidate, writes evidence, or touches the audit
ledger or identity gate. See src/ai/provider.py for the interface contract and
docs/HERMES_V3_ARCHITECTURE.md for the full boundary rationale.
"""
