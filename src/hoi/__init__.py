"""Hermes Opportunity Intelligence (HOI).

Opportunity -> approved requirements -> internal matching (existing fitness engine) -> finance-separated
costing -> market benchmarks -> scenario comparison -> human approvals -> approved report.

Design rules enforced here (see docs/HOI_SECURITY_AND_DATA_BOUNDARIES.md):
* probabilistic parsing is advisory and needs human approval; scoring and costing are deterministic;
* compensation never reaches fitness scoring, generic APIs, logs or the audit trail;
* nothing in this package assigns an employee.
"""
