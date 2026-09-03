"""Bind the existing RecruitFlow AI marketplace module to PathlyHire.

Revision ID: 20260903_pathlyhire_config
Revises: 20260902_hive_integrations
Create Date: 2026-09-03
"""

from alembic import op
import sqlalchemy as sa


revision = "20260903_pathlyhire_config"
down_revision = "20260902_hive_integrations"
branch_labels = None
depends_on = None


APP_SLUG = "recruitflow-ai"
SERVICE_KEY = "pathlyhire"
BASE_URL = "https://app.pathly-hire.uk"
LAUNCH_URL = "/integrations/apps/recruitflow-ai/launch"


def upgrade():
    connection = op.get_bind()

    app_module_id = connection.execute(
        sa.text("SELECT id FROM app_module WHERE slug = :slug"),
        {"slug": APP_SLUG},
    ).scalar()

    if app_module_id is None:
        return

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
                SET service_key = :service_key,
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
                "service_key": SERVICE_KEY,
                "base_url": BASE_URL,
            },
        )

    connection.execute(
        sa.text("UPDATE app_module SET launch_url = :launch_url WHERE id = :app_module_id"),
        {"launch_url": LAUNCH_URL, "app_module_id": app_module_id},
    )


def downgrade():
    connection = op.get_bind()

    app_module_id = connection.execute(
        sa.text("SELECT id FROM app_module WHERE slug = :slug"),
        {"slug": APP_SLUG},
    ).scalar()

    if app_module_id is None:
        return

    connection.execute(
        sa.text(
            """
            DELETE FROM app_integration
            WHERE app_module_id = :app_module_id
              AND service_key = :service_key
            """
        ),
        {"app_module_id": app_module_id, "service_key": SERVICE_KEY},
    )

    connection.execute(
        sa.text(
            """
            UPDATE app_module
            SET launch_url = NULL
            WHERE id = :app_module_id
              AND launch_url = :launch_url
            """
        ),
        {"app_module_id": app_module_id, "launch_url": LAUNCH_URL},
    )
