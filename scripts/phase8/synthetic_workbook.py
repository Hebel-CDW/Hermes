"""Fake Skill-Matrix-2025-shaped workbook for tests and UI contract capture.

Every person here is invented. The workbook reproduces the *structures* the Phase 8 parser
handles (people-as-rows sheet, Certificates sheet with a banner row) and one example of
each validation path, so the real-data pipeline can be exercised without the confidential
workbook. Expected outcomes are listed in ``EXPECTED`` and asserted by the tests.
"""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

FAKE_PEOPLE = ("Zephyrine Quillfeather", "Barnaby Oakenshield", "Marigold Thistlewood", "Percival Moonbrook")
CLIENT_LABEL = "example-client-alpha"

EXPECTED = {
    "people": 4,
    "cells_accepted": 6,
    "cells_rejected": 5,
    "rejections_by_reason": {
        "fractional_average": 1,
        "group_or_section_header": 1,
        "missing_name": 1,
        "non_numeric_cell": 1,
        "out_of_range_value": 1,
    },
    "accepted_skill_cells": 4,
    "accepted_account_cells": 2,
    "skill_labels": 2,
    "mapped": 1,  # "Azure Compute" equals a governed ontology skill name exactly
    "pending": 1,  # "Terraform Modules" has no governed mapping
    "rejected": {"client_account": 1, "soft_skill": 1, "culture_fit": 1},
    "certificate_cells": 3,
    "certificates_exact": 2,  # CKA and AZ-104 as whole-token codes
    "certificates_pending": 1,
}


def build(path: Path) -> Path:
    a, b, c, d = FAKE_PEOPLE
    wb = Workbook()
    certs = wb.active
    certs.title = "Certificates"
    certs.append(["Certificates 2025"])
    certs.append(["Name", "Team", "Manager", "Cert 1", "Cert 2"])
    certs.append([a, "Cloud", "Invented Manager", "CKA - Certified Kubernetes Administrator", "Vendor Partner Badge"])
    certs.append([d, "Cloud", "Invented Manager", "AZ-104 Azure Administrator", None])

    azure = wb.create_sheet("Azure")
    azure.append(["Name", "Designation", "Azure Compute", "Terraform Modules", CLIENT_LABEL, "Customer Service", "Culture Fit"])
    azure.append([a, "Engineer", 4, 3, 2, 5, 3])
    azure.append([b, "Engineer", 0, "abc", 2.5, 1, 1])
    azure.append([c, "Engineer", 7, 2, 1, None, None])
    azure.append(["Group Average", None, 3.5, 2.5, 1.5, None, None])
    azure.append([None, "Engineer", 3, None, None, None, None])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
