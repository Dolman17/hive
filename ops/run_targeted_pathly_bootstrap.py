"""Run the existing Pathly bootstrap for one explicitly approved HIVE account.

Required environment variable:
- PATHLY_BOOTSTRAP_EMAIL

This wrapper only changes consultant selection. The underlying bootstrap remains
responsible for Pathly record creation, entitlement activation, SSO proof, and
summary proof. No PII or secret values are printed.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import get_or_create_tenant_settings
from extensions import db
from models import User
from ops import bootstrap_pathly_first_user as bootstrap


def _select_target():
    target = os.getenv("PATHLY_BOOTSTRAP_EMAIL", "").strip().lower()
    if not target:
        raise RuntimeError("PATHLY_BOOTSTRAP_EMAIL is not configured.")

    user = (
        User.query
        .filter(
            db.func.lower(User.email) == target,
            User.is_active.is_(True),
            User.role == "consultant",
        )
        .first()
    )
    if user is None:
        raise RuntimeError("Target HIVE account is not an active consultant.")

    return user, get_or_create_tenant_settings(user)


bootstrap._select_consultant = _select_target

if __name__ == "__main__":
    raise SystemExit(bootstrap.main())
