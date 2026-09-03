"""Bootstrap and prove the first real HIVE -> Pathly production identity.

This idempotent operational utility:
- selects an existing active non-demo HIVE consultant with tenant settings;
- creates or reuses one Pathly Service for that consultant;
- creates or reuses a Pathly admin User with the same email;
- enables the existing HIVE Pathly entitlement;
- ensures the HIVE identity exists;
- performs a real signed HIVE -> Pathly SSO request;
- confirms the service-scoped Pathly summary API succeeds afterwards.

Required environment variables:
- PATHLY_DATABASE_URL
- HIVE_PATHLY_SSO_SECRET
- HIVE_PATHLY_API_TOKEN

No names, emails, passwords, token values, or secret values are printed.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener, urlopen
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from integration_models import AppIntegration
from integration_routes import get_or_create_hive_identity
from models import AppModule, ConsultantAppAccess, TenantSettings, User


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _split_name(value: str) -> tuple[str, str]:
    parts = [part for part in (value or "").strip().split() if part]
    if not parts:
        return "Pathly", "Admin"
    if len(parts) == 1:
        return parts[0], "Admin"
    return parts[0], " ".join(parts[1:])


def _select_consultant() -> tuple[User, TenantSettings]:
    rows = (
        db.session.query(User, TenantSettings)
        .join(TenantSettings, TenantSettings.user_id == User.id)
        .filter(
            User.role == "consultant",
            User.is_active.is_(True),
            ~db.func.lower(User.email).like("%@example.com"),
            ~db.func.lower(User.name).like("%demo%"),
        )
        .order_by(User.id.asc())
        .all()
    )
    if not rows:
        raise RuntimeError("No active non-demo HIVE consultant with tenant settings is available.")
    return rows[0]


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not configured.")
    return value


def _pathly_database_url() -> str:
    value = _required_env("PATHLY_DATABASE_URL")
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql://", 1)
    return value


def _bootstrap_pathly_records(consultant: User, settings: TenantSettings) -> tuple[int, int]:
    first_name, last_name = _split_name(consultant.name)
    service_name = (settings.business_name or consultant.name or "HIVE Pathly Service").strip()
    service_code = f"HIVE-{consultant.id}"
    password_hash = generate_password_hash(secrets.token_urlsafe(48))

    engine = create_engine(_pathly_database_url(), future=True, pool_pre_ping=True)
    with engine.begin() as connection:
        service = connection.execute(
            text(
                """
                SELECT id, name
                FROM services
                WHERE code = :code OR lower(name) = lower(:name)
                ORDER BY CASE WHEN code = :code THEN 0 ELSE 1 END
                LIMIT 1
                """
            ),
            {"code": service_code, "name": service_name},
        ).mappings().first()

        if service is None:
            service_id = connection.execute(
                text(
                    """
                    INSERT INTO services (
                        name, code, is_active, created_at, updated_at
                    ) VALUES (
                        :name, :code, TRUE, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {"name": service_name, "code": service_code},
            ).scalar_one()
        else:
            service_id = service["id"]

        existing_user = connection.execute(
            text(
                """
                SELECT id, service_id
                FROM users
                WHERE lower(email) = lower(:email)
                LIMIT 1
                """
            ),
            {"email": consultant.email},
        ).mappings().first()

        if existing_user is None:
            pathly_user_id = connection.execute(
                text(
                    """
                    INSERT INTO users (
                        first_name,
                        last_name,
                        email,
                        password_hash,
                        role,
                        service_id,
                        is_active,
                        created_at,
                        updated_at
                    ) VALUES (
                        :first_name,
                        :last_name,
                        :email,
                        :password_hash,
                        'admin',
                        :service_id,
                        TRUE,
                        CURRENT_TIMESTAMP,
                        CURRENT_TIMESTAMP
                    )
                    RETURNING id
                    """
                ),
                {
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": consultant.email.lower().strip(),
                    "password_hash": password_hash,
                    "service_id": service_id,
                },
            ).scalar_one()
        else:
            if existing_user["service_id"] not in (None, service_id):
                raise RuntimeError("Existing Pathly user belongs to a different service; bootstrap aborted.")
            pathly_user_id = existing_user["id"]
            connection.execute(
                text(
                    """
                    UPDATE users
                    SET service_id = :service_id,
                        role = 'admin',
                        is_active = TRUE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :user_id
                    """
                ),
                {"service_id": service_id, "user_id": pathly_user_id},
            )

    return service_id, pathly_user_id


def _prove_sso_and_summary(consultant: User, identity, integration: AppIntegration) -> list[str]:
    signing_secret = _required_env("HIVE_PATHLY_SSO_SECRET")
    api_token = _required_env("HIVE_PATHLY_API_TOKEN")

    serializer = URLSafeTimedSerializer(
        signing_secret,
        salt="hive-product-sso-v1:pathly",
    )
    token = serializer.dumps(
        {
            "sub": identity.hive_user_id,
            "tenant": identity.hive_tenant_id,
            "email": consultant.email,
            "name": consultant.name,
            "role": consultant.role,
            "app": "pathly",
            "aud": integration.sso_audience or "pathly",
            "jti": uuid4().hex,
            "iat": datetime.utcnow().isoformat() + "Z",
        }
    )

    base_url = integration.base_url.rstrip("/")
    sso_path = integration.sso_path if integration.sso_path.startswith("/") else f"/{integration.sso_path}"
    target = f"{base_url}{sso_path}?token={quote(token)}"

    opener = build_opener(_NoRedirect())
    try:
        response = opener.open(Request(target, method="GET"), timeout=10)
        sso_status = response.getcode()
        location = response.headers.get("Location", "")
    except HTTPError as exc:
        sso_status = exc.code
        location = exc.headers.get("Location", "")

    if sso_status not in {301, 302, 303, 307, 308}:
        raise RuntimeError(f"Pathly SSO returned unexpected HTTP {sso_status}.")
    if not location or "login" in location.lower():
        raise RuntimeError("Pathly SSO redirected to login instead of an authenticated destination.")

    summary_path = integration.summary_path if integration.summary_path.startswith("/") else f"/{integration.summary_path}"
    summary_url = (
        f"{base_url}{summary_path}?"
        f"{urlencode({'hive_tenant_id': identity.hive_tenant_id})}"
    )
    summary_request = Request(
        summary_url,
        headers={
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urlopen(summary_request, timeout=10) as response:
        summary_status = response.getcode()
        payload = json.loads(response.read().decode("utf-8"))

    if summary_status != 200 or not payload.get("ok") or not isinstance(payload.get("summary"), dict):
        raise RuntimeError(f"Pathly summary verification failed with HTTP {summary_status}.")

    return sorted(payload["summary"].keys())


def main() -> int:
    with app.app_context():
        consultant, settings = _select_consultant()
        app_module = AppModule.query.filter_by(slug="pathly", is_active=True).first()
        if not app_module:
            raise RuntimeError("Active HIVE Pathly AppModule is missing.")

        integration = AppIntegration.query.filter_by(service_key="pathly", is_enabled=True).first()
        if not integration:
            raise RuntimeError("Enabled HIVE Pathly integration is missing.")

        identity = get_or_create_hive_identity(consultant)

        access = ConsultantAppAccess.query.filter_by(
            consultant_id=consultant.id,
            app_module_id=app_module.id,
        ).first()
        if access is None:
            access = ConsultantAppAccess(
                consultant_id=consultant.id,
                app_module_id=app_module.id,
                status="active",
                access_level="standard",
                activated_at=datetime.utcnow(),
            )
            db.session.add(access)
        else:
            access.status = "active"
            access.activated_at = access.activated_at or datetime.utcnow()

        service_id, pathly_user_id = _bootstrap_pathly_records(consultant, settings)
        db.session.commit()

        metric_keys = _prove_sso_and_summary(consultant, identity, integration)

        print(
            "PATHLY_BOOTSTRAP_OK "
            f"consultant_id={consultant.id} "
            f"service_id={service_id} "
            f"pathly_user_id={pathly_user_id} "
            f"identity_ready={bool(identity.hive_user_id and identity.hive_tenant_id)} "
            "sso=ok summary=ok "
            f"summary_keys={','.join(metric_keys)}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
