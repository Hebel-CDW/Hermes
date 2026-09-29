"""Database trust policy — refuse to serve databases whose identities are unsafe.

A database is served only if it carries explicit trust metadata written at
initialisation (``hermes_meta``):

* ``data_classification``          ``synthetic`` or ``real``
* ``identity_secret_fingerprint``  HMAC(secret, constant) — proves the database was
                                   tokenised with the *current* secret without storing it

Rules (``assess_database_trust``):

1. A brand-new empty database is trusted (nothing to protect yet).
2. Missing metadata → untrusted. Legacy databases must be rebuilt explicitly.
3. Fingerprint must match the running secret, or new identities would diverge.
4. ``synthetic`` databases may not contain real-data tables (baseline, account
   context, certificate staging).
5. ``real`` databases are refused in test mode, refused if the running secret is
   a published one, and refused if ANY stored identity is reproducible from a
   published secret (reversible pseudonymisation).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from shared.errors import UntrustedDatabaseError
from shared.models import utc_now
from shared.secrets import PUBLISHED_SECRETS, is_test_mode

if TYPE_CHECKING:
    from shared.db import HermesDB

CLASSIFICATIONS = ("synthetic", "real")
_FINGERPRINT_CONTEXT = b"hermes-db-trust-v1"
REAL_DATA_TABLES = ("baseline_assessments", "account_context", "cert_staging", "phase8_ingest_runs")


def identity_secret_fingerprint(secret: str) -> str:
    return hmac.new(secret.encode("utf-8"), _FINGERPRINT_CONTEXT, hashlib.sha256).hexdigest()[:32]


def _published_token(secret: str, key: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), key.strip().lower().encode("utf-8"), hashlib.sha256)
    return "EMP-" + digest.hexdigest()[:8]


@dataclass(frozen=True)
class TrustAssessment:
    trusted: bool
    reason: str
    classification: Optional[str]
    reversible_identities: int = 0


def mark_database(db: "HermesDB", classification: str, secret: str) -> None:
    """Record trust metadata. Refuses to relabel an existing classification."""
    if classification not in CLASSIFICATIONS:
        raise ValueError(f"classification must be one of {CLASSIFICATIONS}")
    existing = db.get_meta("data_classification")
    if existing and existing != classification:
        raise UntrustedDatabaseError(
            f"database already classified as {existing!r}; refusing to relabel as {classification!r}",
            code="classification_conflict",
        )
    fingerprint = identity_secret_fingerprint(secret)
    stored_fp = db.get_meta("identity_secret_fingerprint")
    if stored_fp and stored_fp != fingerprint:
        raise UntrustedDatabaseError(
            "database was tokenised with a different identity secret", code="identity_secret_mismatch"
        )
    db.set_meta("data_classification", classification)
    db.set_meta("identity_secret_fingerprint", fingerprint)
    db.set_meta("trust_marked_at", utc_now().isoformat())


def count_reversible_identities(db: "HermesDB") -> int:
    """How many stored tokens can be recomputed from a published secret."""
    with db.session() as conn:
        rows = conn.execute("SELECT coded_identity, source_employee_key FROM identity_vault").fetchall()
    return sum(
        1
        for row in rows
        if any(_published_token(pub, row["source_employee_key"]) == row["coded_identity"] for pub in PUBLISHED_SECRETS)
    )


def assess_database_trust(db: "HermesDB", secret: str) -> TrustAssessment:
    with db.session() as conn:
        identities = conn.execute("SELECT COUNT(*) AS n FROM identity_map").fetchone()["n"]
        real_rows = sum(
            conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] for table in REAL_DATA_TABLES
        )
    classification = db.get_meta("data_classification")
    if classification is None:
        if identities == 0 and real_rows == 0:
            return TrustAssessment(True, "empty_database", None)
        return TrustAssessment(False, "missing_trust_metadata", None)
    if classification not in CLASSIFICATIONS:
        return TrustAssessment(False, "unknown_classification", classification)
    if db.get_meta("identity_secret_fingerprint") != identity_secret_fingerprint(secret):
        return TrustAssessment(False, "identity_secret_mismatch", classification)
    if classification == "synthetic":
        if real_rows:
            return TrustAssessment(False, "synthetic_database_contains_real_data_tables", classification)
        return TrustAssessment(True, "synthetic_database", classification)
    # classification == "real"
    if is_test_mode():
        return TrustAssessment(False, "real_database_in_test_mode", classification)
    if secret in PUBLISHED_SECRETS:
        return TrustAssessment(False, "published_identity_secret", classification)
    reversible = count_reversible_identities(db)
    if reversible:
        return TrustAssessment(False, "reversible_identity_mapping", classification, reversible)
    return TrustAssessment(True, "real_database", classification)


def ensure_database_trusted(db: "HermesDB", secret: str) -> TrustAssessment:
    assessment = assess_database_trust(db, secret)
    if not assessment.trusted:
        raise UntrustedDatabaseError(
            f"refusing to serve database {db.path.name}: {assessment.reason}", code=assessment.reason
        )
    return assessment
