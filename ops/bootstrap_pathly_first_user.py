"""Bootstrap the first real HIVE -> Pathly production identity.

This is an idempotent operational utility. It deliberately:
- selects an existing active non-demo HIVE consultant with tenant settings;
- creates or reuses one Pathly Service for that consultant;
- creates or reuses a Pathly admin User with the same email;
- enables the existing HIVE Pathly entitlement;
- ensures the HIVE identity exists;
- does NOT create Pathly HIVE SSO/tenant links, so the real SSO request must do that.

Required environment variable:
- PATHLY_DATABASE_URL

No names, emails, passwords, or secret values are printed.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime

from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

from app import app
from extensions import db
from integration_routes import get_or_create_hive_identity
from models import AppModule, ConsultantAppAccess, TenantSettings, User


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


def _pathly_database_url() -> str:
    value = os.getenv("PATHLY_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("PATHLY_DATABASE_URL is not configured.")
    if value.startswith("postgres://"):
        value = value.replace("postgres://", "postgresql://", 1)
    return value


def main() -> int:
    with app.app_context():
        consultant, settings = _select_consultant()
        app_module = AppModule.query.filter_by(slug="pathly", is_active=True).first()
        if not app_module:
            raise RuntimeError("Active HIVE Pathly AppModule is missing.")

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

        db.session.commit()
        print(
            "PATHLY_BOOTSTRAP_OK "
            f"consultant_id={consultant.id} "
            f"service_id={service_id} "
            f"pathly_user_id={pathly_user_id} "
            f"identity_ready={bool(identity.hive_user_id and identity.hive_tenant_id)}"
        )
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
