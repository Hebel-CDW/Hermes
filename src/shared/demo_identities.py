"""Synthetic demo principal registry — the ONLY identities the local token stub knows.

Security model (prototype):
* The token carries only ``sub``. Roles and coded identity are looked up here and
  in the database **on every request**; nothing in the token or request body can
  assert a role or a coded identity.
* ``employee_key`` values are the synthetic pilot fixture ids (E1001-E1005). The
  coded identity is resolved server-side via ``identity_map``, so it always matches
  the database's own tokenisation secret.
* Outside local/test mode this registry is disabled and every request is refused,
  because no real identity provider is configured (fail closed).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from shared.secrets import is_test_mode

EMPLOYEE = "employee"
MANAGER = "manager"
ADMIN = "admin"


@dataclass(frozen=True)
class DemoPrincipal:
    sub: str
    roles: Tuple[str, ...]
    employee_key: Optional[str]  # synthetic fixture id; None for pure admins
    description: str


DEMO_PRINCIPALS: Dict[str, DemoPrincipal] = {
    p.sub: p
    for p in (
        DemoPrincipal("demo-manager", (MANAGER,), "E1001", "Delivery manager; E1002/E1003 report to them"),
        DemoPrincipal("demo-manager-2", (MANAGER,), "E1004", "Second manager, used to prove request ownership"),
        DemoPrincipal("demo-employee", (EMPLOYEE,), "E1003", "Employee viewing their own evidence"),
        DemoPrincipal("demo-employee-2", (EMPLOYEE,), "E1005", "Second employee, used to prove isolation"),
        DemoPrincipal("demo-admin", (ADMIN,), None, "Administrator for diagnostics and identity admin"),
    )
}


def demo_auth_enabled() -> bool:
    """Registry auth is permitted only in test mode or an explicit local environment."""
    return is_test_mode() or os.getenv("HERMES_ENV", "local").strip().lower() == "local"


def lookup(sub: str) -> Optional[DemoPrincipal]:
    return DEMO_PRINCIPALS.get(sub)
