"""Migration 002 parity and non-regression: both dialect files define the same tables; the base schema is untouched."""

import re
import sqlite3
from pathlib import Path

import pytest

from shared.db import HermesDB, extra_schema_paths

INFRA = Path(__file__).resolve().parents[2] / "infra"
HOI_TABLES = {"opportunities", "opportunity_members", "opportunity_documents", "requirement_versions", "resource_requirements",
              "candidate_shortlists", "capacity_snapshots", "cost_parameters", "fin_loaded_costs", "market_benchmarks",
              "commercial_scenarios", "scenario_assignments", "approval_events", "opportunity_audit", "fin_access_log"}


def tables(sql: str) -> set:
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql))


def test_dialect_files_define_same_tables():
    a = (INFRA / "sqlite" / "002_hoi.sql").read_text()
    b = (INFRA / "postgres" / "002_hoi.sql").read_text()
    assert tables(a) == tables(b) == HOI_TABLES
    assert "strftime" not in b and "REAL NOT NULL" not in b.replace("DOUBLE PRECISION NOT NULL", "")


def test_migration_is_additive_idempotent_and_applied(tmp_path):
    assert [p.name for p in extra_schema_paths("sqlite")] == ["002_hoi.sql"]
    base = tables((INFRA / "sqlite" / "001_schema.sql").read_text())
    assert not base & HOI_TABLES  # no existing table altered or shadowed
    db = HermesDB(tmp_path / "m.db")
    HermesDB(tmp_path / "m.db")  # second open re-runs migrate(): must be a no-op
    con = sqlite3.connect(tmp_path / "m.db")
    have = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert HOI_TABLES <= have and base <= have
    del db


def test_finance_amount_column_holds_ciphertext_only(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_TEST_MODE", "1")
    from hoi.finance import FinanceVault
    db = HermesDB(tmp_path / "f.db")
    FinanceVault(db).add_costs("fin", [{"scope": "role_band", "subject": "X Role", "monthly_cost": "4242.42", "currency": "USD",
                                        "effective_from": "2026-01-01", "source": "S"}])
    con = sqlite3.connect(tmp_path / "f.db")
    enc = con.execute("SELECT monthly_cost_enc FROM fin_loaded_costs").fetchone()[0]
    assert "4242" not in enc and enc.startswith("gAAAA")


def test_check_constraints_refuse_invalid_values_at_the_database(tmp_path):
    """Integrity is enforced by the schema, not only by application code."""
    HermesDB(tmp_path / "c.db")
    con = sqlite3.connect(tmp_path / "c.db")
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("INSERT INTO opportunities (opportunity_id, owner, client_alias, name, currency, contract_type, duration_months) "
                "VALUES ('OPP-2026-AAAAAA','o','c','n','USD','fixed_fee',6)")
    bad = [
        ("opportunities currency", "INSERT INTO opportunities (opportunity_id, owner, client_alias, name, currency, contract_type, duration_months) VALUES ('OPP-2026-BBBBBB','o','c','n','US','fixed_fee',6)"),
        ("opportunities contract_type", "INSERT INTO opportunities (opportunity_id, owner, client_alias, name, currency, contract_type, duration_months) VALUES ('OPP-2026-CCCCCC','o','c','n','USD','barter',6)"),
        ("opportunities duration", "INSERT INTO opportunities (opportunity_id, owner, client_alias, name, currency, contract_type, duration_months) VALUES ('OPP-2026-DDDDDD','o','c','n','USD','fixed_fee',0)"),
        ("approval outcome", "INSERT INTO approval_events (approval_id, opportunity_id, object_type, object_id, approver_role, outcome, actor) VALUES ('a1','OPP-2026-AAAAAA','scenario','s','finance','maybe','x')"),
        ("approval role", "INSERT INTO approval_events (approval_id, opportunity_id, object_type, object_id, approver_role, outcome, actor) VALUES ('a2','OPP-2026-AAAAAA','scenario','s','ceo','approved','x')"),
        ("benchmark basis", "INSERT INTO market_benchmarks (benchmark_id, role, geography, seniority, engagement_type, basis, currency, unit, source, as_of, import_batch, imported_by) VALUES ('b1','r','g','s','contractor','invented','USD','month','src','2026-01-01','b','x')"),
        ("benchmark unit", "INSERT INTO market_benchmarks (benchmark_id, role, geography, seniority, engagement_type, basis, currency, unit, source, as_of, import_batch, imported_by) VALUES ('b2','r','g','s','contractor','bill_rate','USD','week','src','2026-01-01','b','x')"),
        ("loaded-cost scope", "INSERT INTO fin_loaded_costs (cost_id, scope, subject_key, monthly_cost_enc, currency, cost_basis, effective_from, source, entered_by) VALUES ('c1','team','x','enc','USD','fully_loaded_monthly','2026-01-01','s','f')"),
        ("loaded-cost basis (never mixed)", "INSERT INTO fin_loaded_costs (cost_id, scope, subject_key, monthly_cost_enc, currency, cost_basis, effective_from, source, entered_by) VALUES ('c2','individual','x','enc','USD','base_salary','2026-01-01','s','f')"),
        ("requirement status", "INSERT INTO requirement_versions (version_id, opportunity_id, version_no, status, parser_version, extraction_method, created_by) VALUES ('v1','OPP-2026-AAAAAA',1,'maybe','p','m','u')"),
        ("shortlist eligibility", "INSERT INTO candidate_shortlists (shortlist_id, match_run_id, opportunity_id, version_id, requirement_id, coded_identity, rank, fitness_score, eligibility, staffing_request_id, requested_by) VALUES ('s1','m','OPP-2026-AAAAAA','v','r','EMP-00000000',1,0.5,'probably','q','u')"),
        ("scenario status", "INSERT INTO commercial_scenarios (scenario_id, opportunity_id, version_id, kind, currency, months, assumption_json, calc_version, input_hash, result_json, status, created_by) VALUES ('sc1','OPP-2026-AAAAAA','v','internal','USD',6,'{}','c','h','{}','shipped','u')"),
        ("scenario months", "INSERT INTO commercial_scenarios (scenario_id, opportunity_id, version_id, kind, currency, months, assumption_json, calc_version, input_hash, result_json, created_by) VALUES ('sc2','OPP-2026-AAAAAA','v','internal','USD',500,'{}','c','h','{}','u')"),
        ("unknown opportunity (FK)", "INSERT INTO opportunity_members (opportunity_id, sub, member_role, added_by) VALUES ('OPP-2026-ZZZZZZ','x','sales','y')"),
    ]
    for name, sql in bad:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(sql)
    con.close()
