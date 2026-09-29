"""Application service wiring engines to SQLite for local-first runtime."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from fitness_gap.engine import FitnessGapEngine
from identity_abstraction.gate import IdentityAbstractionGate
from identity_resolution.gateway import IdentityResolutionGateway, ResolutionDenied
from shared.audit import AuditLedger
from shared.db import HermesDB
from shared.db_trust import TrustAssessment, assess_database_trust, mark_database
from shared.errors import (
    DecisionValidationError,
    RequestNotFound,
    RequestOwnershipError,
    RequestStateConflict,
    UnknownSkillError,
)
from shared.excel_sunset import (
    kill_gate,
    map_cert_label,
    pending_alias_inbox,
    survey_matrix as read_survey_matrix,
)
from shared.models import (
    CertifiedEvidence,
    DeclaredEvidence,
    EvidenceRecord,
    EvidenceType,
    ProficiencyLevel,
    RankedCandidate,
    SkillRecord,
    StaffingRequest,
    TargetRoleProfile,
    utc_now,
)
from shared.secrets import require_identity_map_secret
from shared.taxonomy import load_taxonomy
from skill_inference.engine import SkillInferenceEngine


class HermesService:
    def __init__(self, db: Optional[HermesDB] = None, mapping_secret: Optional[str] = None) -> None:
        self.db = db or HermesDB()
        secret = require_identity_map_secret(mapping_secret)
        # Kept private: used only to fingerprint the database for trust checks.
        self._identity_secret = secret
        # Hydrate existing map from DB first so tokens stay stable
        existing = self._load_existing_map()
        self.gate = IdentityAbstractionGate(secret, existing_map=existing)
        self._hydrate_display_names()
        self.audit = AuditLedger(db=self.db)
        self.inference = SkillInferenceEngine()
        tax = load_taxonomy()
        adjacency = {}
        skill_decay = {}
        for s in tax.all_skills():
            related = list(getattr(s, "related_skills", None) or []) + list(
                getattr(s, "relations", None) or []
            )
            if related:
                adjacency[s.skill_id] = list(dict.fromkeys(related))
            # Display-only: lets the inspector show which half-life produced a
            # freshness value. Mirrors SkillInferenceEngine.half_life_for_skill.
            skill_decay[s.skill_id] = {
                "decay_class": s.decay_class,
                "half_life_days": self.inference.half_life_for_skill(s.skill_id),
            }
        demand = self.db.get_demand()
        self.fitness = FitnessGapEngine(
            audit=self.audit,
            demand_weights=demand,
            adjacency=adjacency,
            skill_decay=skill_decay,
        )
        self.resolution = IdentityResolutionGateway(self.gate, audit=self.audit)
        self.last_computation_run_id = ""

    # ------------------------------------------------------------- DB trust
    def mark_database(self, classification: str) -> None:
        """Record trust metadata for the database (``synthetic`` or ``real``)."""
        mark_database(self.db, classification, self._identity_secret)

    def assess_trust(self) -> TrustAssessment:
        return assess_database_trust(self.db, self._identity_secret)

    def _load_existing_map(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, source_employee_key FROM identity_vault"
            ).fetchall()
        for row in rows:
            out[row["source_employee_key"].strip().lower()] = row["coded_identity"]
        return out

    def _hydrate_display_names(self) -> None:
        with self.db.session() as conn:
            rows = conn.execute(
                "SELECT coded_identity, display_name, source_employee_key FROM identity_vault"
            ).fetchall()
        for row in rows:
            key = row["source_employee_key"].strip().lower()
            token = row["coded_identity"]
            self.gate._forward[key] = token
            self.gate._reverse[token] = key
            self.gate._display_names[token] = row["display_name"]

    def abstract(self, raw: Mapping[str, Any], employee_key_field: str = "employee_id") -> Dict[str, Any]:
        # Prefer DB-stored token for known source keys
        employee_key = str(raw[employee_key_field]).strip().lower()
        stored = self.db.resolve_coded_for_source(employee_key)
        if stored:
            self.gate._forward[employee_key] = stored
            self.gate._reverse[stored] = employee_key
        result = self.gate.abstract_record(raw, employee_key_field=employee_key_field)
        self.gate.assert_no_pii(result.record)
        display = self.gate._display_names.get(result.coded_identity, employee_key)
        self.db.upsert_identity(result.coded_identity, employee_key, display_name=display)
        # Re-read authority token after upsert
        authority = self.db.resolve_coded_for_source(employee_key) or result.coded_identity
        if authority != result.coded_identity:
            self.gate._forward[employee_key] = authority
            self.gate._reverse[authority] = employee_key
            result = type(result)(
                coded_identity=authority,
                record={**result.record, "coded_identity": authority},
                stripped_fields=result.stripped_fields,
            )
        self.db.set_availability(authority, True)
        self.audit.append(
            "evidence_ingestion",
            actor="ingest",
            payload={"coded_identity": authority},
        )
        return {
            "coded_identity": authority,
            "record": result.record,
            "stripped_fields": list(result.stripped_fields),
        }

    def stage_and_merge(
        self,
        evidence: Sequence[EvidenceRecord],
        as_of: Optional[datetime] = None,
        computation_run_id: Optional[str] = None,
    ) -> List[SkillRecord]:
        """Stage evidence and recompute the matrix.

        Evidence for a skill outside the governed ontology is rejected before anything
        is staged — unmapped labels must never become scored skills.

        ``as_of`` pins the clock used for freshness decay. Left unset (the default)
        it is "now", which means scores drift as evidence ages — correct for
        production, fatal for a reproducible demo. Passing an explicit ``as_of``
        together with a fixed ``computation_run_id`` makes a run byte-reproducible.
        """
        unknown = sorted(
            {e.skill_id for e in evidence if self.inference.taxonomy.skill_by_id(e.skill_id) is None}
        )
        if unknown:
            raise UnknownSkillError(f"evidence references skills outside the ontology: {unknown}")
        for item in evidence:
            with self.db.session() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM identity_map WHERE coded_identity = ?",
                    (item.coded_identity,),
                ).fetchone()
            if not exists:
                self.db.upsert_identity(
                    item.coded_identity, item.coded_identity, display_name=item.coded_identity
                )
            self.db.stage_evidence(item)
        all_evidence = self.db.load_all_evidence()
        merged = self.inference.merge_evidence(all_evidence, as_of=as_of)
        run_id = computation_run_id or str(uuid.uuid4())
        self.last_computation_run_id = run_id
        self.db.replace_skills_matrix(merged, computation_run_id=run_id)
        self.audit.append(
            "inference_computation",
            actor="skill_inference",
            payload={"count": len(merged), "computation_run_id": run_id},
        )
        return merged

    def rank(
        self,
        request: StaffingRequest,
        availability: Optional[Mapping[str, bool]] = None,
        critical_skills: Optional[Sequence[str]] = None,
        min_coverage_ratio: Optional[float] = None,
    ):
        existing = self.db.get_staffing_request(request.request_id)
        if existing is not None:
            # Ownership is immutable and checked before any scoring or audit happens.
            if existing["requester_id"] != request.requester_id:
                raise RequestOwnershipError("staffing request is owned by another principal")
            if existing["status"] != "open":
                raise RequestStateConflict("staffing request already has a recorded decision")
        matrix = self.db.load_skills_matrix()
        alloc = dict(self.db.get_allocation())
        if availability:
            for k, v in availability.items():
                alloc[k] = 1.0 if v else 0.0
        self.fitness.demand_weights = self.db.get_demand()
        # Source refs power the inspector's evidence drill-down (ticket/cert ids only).
        self.fitness.evidence_source_refs = self.db.evidence_source_refs_by_skill()
        run_id = self.last_computation_run_id
        if not run_id:
            # Prefer the run id stamped on the matrix rows we just loaded, so the
            # ranking always cites the run it actually read.
            stamped = {r.computation_run_id for r in matrix if r.computation_run_id}
            run_id = sorted(stamped)[0] if len(stamped) == 1 else ""
        result = self.fitness.rank_candidates(
            request,
            matrix,
            allocation=alloc,
            computation_run_id=run_id or "",
            critical_skills=critical_skills,
            min_coverage_ratio=min_coverage_ratio,
        )
        self.db.save_staffing_request(
            request.request_id,
            request.requester_id,
            [c.coded_identity for c in result.candidates],
            computation_run_id=run_id or "",
            excluded=result.excluded_candidates,
            result=result.model_dump(mode="json"),
            requirements={
                "required_skills": {k: int(v) for k, v in request.required_skills.items()},
                "critical_skills": sorted(critical_skills or []),
                "min_coverage_ratio": min_coverage_ratio,
                "shortlist_size": request.shortlist_size,
            },
        )
        return result

    def gaps(self, coded_identity: str, role: TargetRoleProfile):
        matrix = self.db.load_skills_matrix()
        self.fitness.demand_weights = self.db.get_demand()
        return self.fitness.compute_gaps(coded_identity, role, matrix)

    def resolve(self, request_id: str, requester_id: str) -> List[Dict[str, str]]:
        stored = self.db.get_staffing_request(request_id)
        if not stored:
            raise ResolutionDenied("unknown staffing request")
        if stored["requester_id"] != requester_id:
            raise ResolutionDenied("requester does not own this staffing request")
        shortlist = [
            RankedCandidate(
                coded_identity=t,
                fitness_score=0.0,
                rank=i + 1,
                per_skill_reasoning={},
                evidence_ids=[],
            )
            for i, t in enumerate(stored["shortlist"])
        ]
        self._hydrate_display_names()
        return self.resolution.resolve_shortlist(
            request_id=request_id,
            requester_id=requester_id,
            shortlist=shortlist,
            allowed_requester_id=stored["requester_id"],
        )

    def decide(
        self,
        request_id: str,
        approved_by: str,
        status: str,
        chosen_coded_identity: Optional[str] = None,
        rejection_reason: Optional[str] = None,
        override_note: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record the human decision for a ranked request.

        ``approved_by`` must be the authenticated principal (the API passes it from
        the verified token, never from the body). Rules, in order:
        request exists (404) -> caller owns it (403) -> still open (409) ->
        a ranking produced a shortlist (422) -> an accepted/overridden decision names
        a candidate (422) -> that candidate was not excluded (422) -> and is on the
        shortlist (422).
        """
        stored = self.db.get_staffing_request(request_id)
        if not stored:
            raise RequestNotFound("unknown staffing request")
        if stored["requester_id"] != approved_by:
            raise RequestOwnershipError("only the requesting manager may decide this request")
        if stored["status"] != "open":
            raise RequestStateConflict("a decision has already been recorded for this request")
        shortlist = list(stored["shortlist"])
        if not shortlist:
            raise DecisionValidationError(
                "request has no ranked shortlist to decide on", code="no_shortlist"
            )
        if status in {"accepted", "overridden"} and not chosen_coded_identity:
            raise DecisionValidationError(
                f"a {status} decision must name the chosen candidate", code="candidate_required"
            )
        if chosen_coded_identity:
            excluded = {e.get("coded_identity"): e.get("reason") for e in stored.get("excluded", [])}
            if chosen_coded_identity in excluded:
                raise DecisionValidationError(
                    f"candidate was excluded by the engine ({excluded[chosen_coded_identity]})",
                    code="candidate_excluded",
                )
            if chosen_coded_identity not in shortlist:
                raise DecisionValidationError(
                    "candidate is not on the generated shortlist", code="candidate_not_shortlisted"
                )
        rank_of = shortlist.index(chosen_coded_identity) + 1 if chosen_coded_identity else None
        self.db.record_staffing_decision(
            request_id=request_id,
            status=status,
            approved_by=approved_by,
            chosen_coded_identity=chosen_coded_identity,
            rejection_reason=rejection_reason,
            override_note=override_note,
            engine_rank_of_choice=rank_of,
        )
        # Guardrail 8: never feed decisions back into scoring — audit only
        self.audit.append(
            "staffing_decision",
            actor=approved_by,
            payload={
                "request_id": request_id,
                "status": status,
                "chosen_coded_identity": chosen_coded_identity,
                "engine_rank_of_choice": rank_of,
                "override_note": override_note,
                "rejection_reason": rejection_reason,
                "guardrail": "never_score_on_historical_staffing_decisions",
            },
        )
        return self.db.get_staffing_request(request_id) or {}

    def me(self, coded_identity: str) -> Dict[str, Any]:
        matrix = [r for r in self.db.load_skills_matrix() if r.coded_identity == coded_identity]
        evidence = self.db.evidence_for_identity(coded_identity)
        return {
            "coded_identity": coded_identity,
            "skills": [m.model_dump(mode="json") for m in matrix],
            "evidence": [
                {
                    "evidence_id": e["evidence_id"],
                    "skill_id": e["skill_id"],
                    "evidence_type": e["evidence_type"],
                    "source_ref": e["source_ref"],
                    "occurred_at": e["occurred_at"],
                    "payload": __import__("json").loads(e["payload_json"] or "{}"),
                }
                for e in evidence
            ],
        }

    def contest(
        self, coded_identity: str, reason: str, skill_id: Optional[str] = None
    ) -> Dict[str, str]:
        contest_id = str(uuid.uuid4())
        self.db.add_contest(contest_id, coded_identity, skill_id, reason)
        self.audit.append(
            "evidence_contest",
            actor=coded_identity,
            payload={"contest_id": contest_id, "skill_id": skill_id, "reason": reason},
        )
        return {"contest_id": contest_id, "status": "open"}

    def skill_review(self, coded_identity: str) -> Dict[str, Any]:
        if not self.db.has_coded_identity(coded_identity):
            raise RequestNotFound("unknown coded identity")
        matrix = [r for r in self.db.load_skills_matrix() if r.coded_identity == coded_identity]
        sources: Dict[str, set] = {}
        for row in self.db.evidence_for_identity(coded_identity):
            sources.setdefault(row["skill_id"], set()).add(row["evidence_type"])
        return {
            "coded_identity": coded_identity,
            "matrix": [
                {
                    "skill_id": rec.skill_id,
                    "proficiency": int(rec.proficiency),
                    "confidence": rec.confidence,
                    "freshness": rec.freshness,
                    "volume_score": rec.volume_score,
                    "sources": sorted(sources.get(rec.skill_id, ())),
                }
                for rec in sorted(matrix, key=lambda r: r.skill_id)
            ],
            "contests": self.db.list_open_contests(coded_identity),
        }

    def declare_skill(
        self,
        actor_sub: str,
        coded_identity: str,
        skill_id: str,
        proficiency: int,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.db.has_coded_identity(coded_identity):
            raise RequestNotFound("unknown coded identity")
        if self.inference.taxonomy.skill_by_id(skill_id) is None:
            raise UnknownSkillError(f"unknown skill id: {skill_id}")
        evidence_id = f"mgr-decl-{uuid.uuid4()}"
        record = DeclaredEvidence(
            evidence_id=evidence_id,
            coded_identity=coded_identity,
            skill_id=skill_id,
            proficiency=ProficiencyLevel(proficiency),
            occurred_at=utc_now(),
            source_ref=f"mgr:{actor_sub}",
            manager_confirmed=True,
            metadata={"manager_confirmed": True},
        )
        self.stage_and_merge([record])
        payload: Dict[str, Any] = {
            "coded_identity": coded_identity,
            "skill_id": skill_id,
            "actor": actor_sub,
            "evidence_id": evidence_id,
            "proficiency": proficiency,
        }
        if note:
            payload["note"] = note
        self.audit.append("manager_declared_skill", actor=actor_sub, payload=payload)
        return {
            "status": "saved",
            "coded_identity": coded_identity,
            "skill_id": skill_id,
            "evidence_id": evidence_id,
        }

    def resolve_contest(self, actor_sub: str, contest_id: str, status: str) -> Dict[str, str]:
        contest = self.db.get_contest(contest_id)
        if not contest:
            raise RequestNotFound("unknown contest")
        if contest["status"] != "open":
            raise RequestStateConflict("contest is not open")
        if status == "confirmed":
            skill_id = contest.get("skill_id")
            if not skill_id:
                raise UnknownSkillError("contest has no skill to confirm")
            level = 3
            for rec in self.db.load_skills_matrix():
                if rec.coded_identity == contest["coded_identity"] and rec.skill_id == skill_id:
                    level = int(rec.proficiency)
                    break
            self.declare_skill(actor_sub, contest["coded_identity"], skill_id, level)
        self.db.set_contest_status(contest_id, status)
        self.audit.append(
            "manager_contest_resolved",
            actor=actor_sub,
            payload={
                "contest_id": contest_id,
                "coded_identity": contest["coded_identity"],
                "skill_id": contest.get("skill_id"),
                "status": status,
            },
        )
        return {"contest_id": contest_id, "status": status}

    def taxonomy_pending(self) -> Dict[str, Any]:
        return pending_alias_inbox(self.db)

    def resolve_taxonomy_alias(
        self,
        actor_sub: str,
        alias_label: str,
        decision: str,
        skill_id: Optional[str] = None,
    ) -> Dict[str, str]:
        from phase8.workbook import normalize_label

        label = alias_label.strip()
        if not label:
            raise DecisionValidationError("alias_label is required")
        action = decision.strip().lower()
        if action == "reject":
            self.db.upsert_skill_alias(label, "", 0.0, "rejected")
            key = normalize_label(label)
            if key and key != label:
                self.db.upsert_skill_alias(key, "", 0.0, "rejected")
            self.audit.append(
                "taxonomy_alias_rejected",
                actor=actor_sub,
                payload={"alias_label": label},
            )
            return {"alias_label": label, "mapped_by": "rejected", "skill_id": ""}
        if action != "approve":
            raise DecisionValidationError("decision must be approve or reject")
        if not skill_id or self.inference.taxonomy.skill_by_id(skill_id) is None:
            raise UnknownSkillError(f"unknown skill id: {skill_id}")
        self.db.upsert_skill_alias(label, skill_id, 1.0, "human")
        key = normalize_label(label)
        if key and key != label:
            self.db.upsert_skill_alias(key, skill_id, 1.0, "human")
        self.db.rebind_baseline_skill_ids(label, skill_id)
        self.audit.append(
            "taxonomy_alias_approved",
            actor=actor_sub,
            payload={"alias_label": label, "skill_id": skill_id, "mapped_by": "human"},
        )
        return {"alias_label": label, "mapped_by": "human", "skill_id": skill_id}

    def survey_matrix(self) -> Dict[str, Any]:
        return read_survey_matrix(self.db)

    def excel_sunset(self) -> Dict[str, Any]:
        return kill_gate(self.db)

    def ingest_tickets(self, tickets: Sequence[Mapping[str, Any]], actor_sub: str) -> Dict[str, int]:
        ingested = 0
        scored = 0
        staged: List[EvidenceRecord] = []
        for raw in tickets:
            employee_id = str(raw.get("employee_id") or "").strip()
            ticket_number = str(raw.get("ticket_number") or "").strip()
            text = str(raw.get("short_description") or "").strip()
            resolved = str(raw.get("resolved_at") or "").strip()
            if not employee_id or not ticket_number or not text or not resolved:
                raise DecisionValidationError("each ticket needs employee_id, ticket_number, short_description, resolved_at")
            coded = self.db.resolve_coded_for_source(employee_id)
            if not coded:
                continue
            occurred = datetime.fromisoformat(resolved.replace("Z", "+00:00"))
            records = self.inference.infer_from_ticket(
                coded, text, occurred, ticket_number, ticket_number
            )
            ingested += 1
            scored += len(records)
            staged.extend(records)
        if staged:
            self.stage_and_merge(staged)
        self.audit.append(
            "tickets_ingested",
            actor=actor_sub,
            payload={"ingested": ingested, "scored": scored},
        )
        return {"ingested": ingested, "scored": scored}

    def date_certificate(self, staging_id: str, earned_at: str, actor_sub: str) -> Dict[str, str]:
        row = self.db.get_cert_staging(staging_id)
        if not row:
            raise RequestNotFound("unknown certificate staging id")
        occurred = datetime.fromisoformat(earned_at.replace("Z", "+00:00"))
        iso = occurred.isoformat()
        self.db.set_cert_earned_at(staging_id, iso)
        self.audit.append(
            "certificate_dated",
            actor=actor_sub,
            payload={"staging_id": staging_id, "earned_at": iso},
        )
        return {"staging_id": staging_id, "earned_at": iso}

    def promote_certificate(self, staging_id: str, actor_sub: str) -> Dict[str, int]:
        row = self.db.get_cert_staging(staging_id)
        if not row:
            raise RequestNotFound("unknown certificate staging id")
        earned = (row.get("earned_at") or "").strip()
        if not earned:
            raise DecisionValidationError("certificate has no earned_at; date it before promotion")
        if int(row.get("promoted") or 0) == 1:
            return {"promoted": 1}
        code_to_skill = {
            code: skill.skill_id
            for skill in self.inference.taxonomy.all_skills()
            for code in skill.cert_codes
        }
        skill_id, cert_code = map_cert_label(self.db, row["cert_label"], code_to_skill)
        if not skill_id:
            raise UnknownSkillError("certificate label is not mapped to a governed skill")
        occurred = datetime.fromisoformat(str(earned).replace("Z", "+00:00"))
        record = CertifiedEvidence(
            evidence_id=f"cert-{staging_id}",
            coded_identity=row["coded_identity"],
            skill_id=skill_id,
            evidence_type=EvidenceType.CERTIFIED,
            proficiency=ProficiencyLevel.PROFICIENT,
            occurred_at=occurred,
            source_ref=cert_code or row["cert_label"],
            metadata={"source_ref": cert_code or row["cert_label"]},
        )
        self.stage_and_merge([record])
        self.db.mark_cert_promoted(staging_id, cert_code)
        self.audit.append(
            "certificate_promoted",
            actor=actor_sub,
            payload={"staging_id": staging_id, "skill_id": skill_id, "coded_identity": row["coded_identity"]},
        )
        return {"promoted": 1}

    def bind_principal(self, actor_sub: str, sub: str, coded_identity: str) -> Dict[str, str]:
        if not self.db.has_coded_identity(coded_identity):
            raise RequestNotFound("unknown coded identity")
        self.db.bind_principal(sub, coded_identity, mapped_by="human")
        self.audit.append(
            "principal_bound",
            actor=actor_sub,
            payload={"sub": sub, "coded_identity": coded_identity, "mapped_by": "human"},
        )
        return {"sub": sub, "coded_identity": coded_identity, "mapped_by": "human"}

    def add_org_edge(self, actor_sub: str, manager_coded_id: str, report_coded_id: str) -> Dict[str, str]:
        if not self.db.has_coded_identity(manager_coded_id) or not self.db.has_coded_identity(report_coded_id):
            raise RequestNotFound("unknown coded identity")
        if manager_coded_id == report_coded_id:
            raise DecisionValidationError("manager and report must be different people")
        self.db.add_org_edge(manager_coded_id, report_coded_id)
        self.audit.append(
            "org_edge_approved",
            actor=actor_sub,
            payload={"manager_coded_id": manager_coded_id, "report_coded_id": report_coded_id, "mapped_by": "human"},
        )
        return {"manager_coded_id": manager_coded_id, "report_coded_id": report_coded_id}
