"""Bind Pathly to the HIVE marketplace.

Revision ID: 20260903_pathly_config
Revises: 20260903_ellipsecrm_config
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_pathly_config"
down_revision = "20260903_ellipsecrm_config"
branch_labels = None
depends_on = None


APP_SLUG = "pathly"
APP_NAME = "Pathly"
SERVICE_KEY = "pathly"
BASE_URL = "https://pathly-production-7b99.up.railway.app"
LAUNCH_URL = "/integrations/apps/pathly/launch"


def _app_module_id(connection):
    app_module_id = connection.execute(
        sa.text("SELECT id FROM app_module WHERE slug = :slug"),
        {"slug": APP_SLUG},
    ).scalar()
    if app_module_id is not None:
        return app_module_id

    app_module_id = connection.execute(
        sa.text("SELECT id FROM app_module WHERE lower(name) = lower(:name)"),
        {"name": APP_NAME},
    ).scalar()
    if app_module_id is not None:
        return app_module_id

    return connection.execute(
        sa.text(
            """
            INSERT INTO app_module (
                name,
                slug,
                description,
                required_tier,
                icon,
                launch_url,
                is_active,
                is_core,
                created_at
            ) VALUES (
                :name,
                :slug,
                'Learning, training pathways and compliance tracking for consultant clients.',
                'professional',
                NULL,
                NULL,
                TRUE,
                FALSE,
                CURRENT_TIMESTAMP
            )
            RETURNING id
            """
        ),
        {"name": APP_NAME, "slug": APP_SLUG},
    ).scalar_one()


def upgrade():
    connection = op.get_bind()
    app_module_id = _app_module_id(connection)

    integration_id = connection.execute(
        sa.text("SELECT id FROM app_integration WHERE service_key = :service_key"),
        {"service_key": SERVICE_KEY},
    ).scalar()

    if integration_id is None:
        integration_id = connection.execute(
            sa.text("SELECT id FROM app_integration WHERE app_module_id = :app_module_id"),
            {"app_module_id": app_module_id},
        ).scalar()

    if integration_id is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO app_integration (
                    app_module_id,
                    service_key,
                    base_url,
                    sso_path,
                    sso_audience,
                    event_token_env,
                    summary_path,
                    health_path,
                    is_enabled,
                    created_at,
                    updated_at
                ) VALUES (
                    :app_module_id,
                    :service_key,
                    :base_url,
                    '/auth/hive-sso',
                    :service_key,
                    NULL,
                    '/api/v1/summary',
                    '/api/v1/health',
                    TRUE,
                    CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP
                )
                """
            ),
            {
                "app_module_id": app_module_id,
                "service_key": SERVICE_KEY,
                "base_url": BASE_URL,
            },
        )
    else:
        connection.execute(
            sa.text(
                """
                UPDATE app_integration
                SET app_module_id = :app_module_id,
                    service_key = :service_key,
                    base_url = :base_url,
                    sso_path = '/auth/hive-sso',
                    sso_audience = :service_key,
                    summary_path = '/api/v1/summary',
                    health_path = '/api/v1/health',
                    is_enabled = TRUE,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :integration_id
                """
            ),
            {
                "integration_id": integration_id,
                "app_module_id": app_module_id,
                "service_key": SERVICE_KEY,
                "base_url": BASE_URL,
            },
        )

    connection.execute(
        sa.text(
            """
            UPDATE app_module
            SET launch_url = :launch_url,
                is_active = TRUE
            WHERE id = :app_module_id
            """
        ),
        {"launch_url": LAUNCH_URL, "app_module_id": app_module_id},
    )


def downgrade():
    connection = op.get_bind()

    integration = connection.execute(
        sa.text(
            """
            SELECT app_module_id
            FROM app_integration
            WHERE service_key = :service_key
            """
        ),
        {"service_key": SERVICE_KEY},
    ).first()

    connection.execute(
        sa.text("DELETE FROM app_integration WHERE service_key = :service_key"),
        {"service_key": SERVICE_KEY},
    )

    if integration is not None:
        connection.execute(
            sa.text(
                """
                UPDATE app_module
                SET launch_url = NULL
                WHERE id = :app_module_id
                  AND launch_url = :launch_url
                """
            ),
            {
                "app_module_id": integration.app_module_id,
                "launch_url": LAUNCH_URL,
            },
        )
