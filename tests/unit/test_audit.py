from shared.audit import AuditLedger


def test_audit_append_only():
    ledger = AuditLedger()
    e1 = ledger.append("inference_computation", "system", {"n": 1})
    e2 = ledger.append("fitness_ranking", "mgr", {"n": 2})
    assert len(ledger.all_events()) == 2
    assert ledger.by_type("fitness_ranking")[0].event_id == e2.event_id
    assert e1.event_id != e2.event_id
