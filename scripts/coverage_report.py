"""Compute pilot evidence coverage from fixture pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from identity_abstraction.gate import IdentityAbstractionGate
from shared.models import EvidenceRecord, EvidenceType, ProficiencyLevel
from skill_inference.engine import SkillInferenceEngine


def main() -> int:
    fixture = json.loads(Path("data/fixtures/pilot_population.json").read_text())
    gate = IdentityAbstractionGate("fixture-secret")
    engine = SkillInferenceEngine()
    evidence = []
    for ticket in fixture["tickets"]:
        abs_rec = gate.abstract_record(ticket)
        occurred = datetime.fromisoformat(ticket["resolved_at"].replace("Z", "+00:00"))
        evidence.extend(
            engine.infer_from_ticket(
                abs_rec.coded_identity,
                ticket["short_description"],
                occurred,
                ticket["ticket_number"],
                ticket["ticket_number"],
            )
        )
    for cert in fixture["certifications"]:
        abs_rec = gate.abstract_record(cert)
        evidence.append(
            EvidenceRecord(
                evidence_id=f"cert-{cert['cert_code']}-{cert['employee_id']}",
                coded_identity=abs_rec.coded_identity,
                skill_id=cert["skill_id"],
                evidence_type=EvidenceType.CERTIFIED,
                proficiency=ProficiencyLevel(cert["proficiency"]),
                occurred_at=datetime.fromisoformat(cert["earned_at"].replace("Z", "+00:00")),
                source_ref=cert["cert_code"],
            )
        )
    covered = set(engine.ensure_coverage(evidence))
    # Map employee ids to tokens for population
    population_tokens = {gate.tokenize(p["employee_id"]) for p in fixture["pilot_population"]}
    # Coverage = identities with demonstrated evidence from tickets
    demo_ids = {e.coded_identity for e in evidence if e.evidence_type == EvidenceType.DEMONSTRATED}
    coverage = len(demo_ids & population_tokens) / max(1, len(population_tokens))
    report = {
        "pilot_size": len(population_tokens),
        "with_demonstrated": len(demo_ids & population_tokens),
        "coverage_pct": round(coverage * 100, 2),
        "meets_80": coverage >= 0.8,
        "skills_scored": len(engine.merge_evidence(evidence)),
    }
    print(json.dumps(report, indent=2))
    return 0 if report["meets_80"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
