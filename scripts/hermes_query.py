"""Local CLI replacing Copilot Studio for staffing and learning-path queries."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from shared.db import HermesDB
from shared.models import ProficiencyLevel, StaffingRequest, TargetRoleProfile
from shared.service import HermesService
from scripts.narrate import assert_grounded_staffing, narrate_gaps, narrate_staffing


def _svc(db_path: Path) -> HermesService:
    os.environ["HERMES_DB_PATH"] = str(db_path)
    return HermesService(db=HermesDB(db_path), mapping_secret=os.getenv("IDENTITY_MAP_SECRET", "fixture-secret"))


def cmd_staff(args: argparse.Namespace) -> int:
    svc = _svc(args.db)
    skills = json.loads(args.skills) if args.skills.startswith("{") else {args.skills: args.level}
    request = StaffingRequest(
        request_id=args.request_id,
        requester_id=args.requester,
        required_skills={k: ProficiencyLevel(int(v)) for k, v in skills.items()},
        shortlist_size=args.shortlist,
    )
    result = svc.rank(request)
    payload = result.model_dump(mode="json")
    assert_grounded_staffing(payload)
    resolved = None
    if args.resolve:
        resolved = svc.resolve(args.request_id, args.requester)
    print(narrate_staffing(payload, resolved))
    if args.json:
        print(json.dumps({"result": payload, "resolved": resolved}, indent=2, default=str))
    return 0


def cmd_gaps(args: argparse.Namespace) -> int:
    svc = _svc(args.db)
    role_data = svc.db.get_role(args.role)
    if not role_data:
        raise SystemExit(f"unknown role: {args.role}")
    role = TargetRoleProfile(
        role_id=role_data["role_id"],
        role_name=role_data["role_name"],
        required_skills={k: ProficiencyLevel(int(v)) for k, v in role_data["required_skills"].items()},
    )
    # allow EMP token or employee_id
    coded = args.identity
    if not coded.startswith("EMP-"):
        coded = svc.gate.tokenize(coded)
    result = svc.gaps(coded, role)
    payload = result.model_dump(mode="json")
    print(narrate_gaps(payload))
    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Hermes local query CLI")
    parser.add_argument("--db", type=Path, default=Path(os.getenv("HERMES_DB_PATH", "data/hermes.db")))
    sub = parser.add_subparsers(dest="cmd", required=True)

    staff = sub.add_parser("staff", help="Rank candidates for a skill profile")
    staff.add_argument("--skills", required=True, help='JSON map or single skill_id')
    staff.add_argument("--level", type=int, default=3)
    staff.add_argument("--request-id", default="cli-staff-1")
    staff.add_argument("--requester", default="mgr-cli")
    staff.add_argument("--shortlist", type=int, default=3)
    staff.add_argument("--resolve", action="store_true")
    staff.add_argument("--json", action="store_true")
    staff.set_defaults(func=cmd_staff)

    gaps = sub.add_parser("gaps", help="Compute learning-path gaps")
    gaps.add_argument("identity", help="EMP-#### or employee_id")
    gaps.add_argument("--role", default="senior_cloud_engineer")
    gaps.add_argument("--json", action="store_true")
    gaps.set_defaults(func=cmd_gaps)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
