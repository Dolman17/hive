"""Add HIVE integration platform tables

Revision ID: 20260902_hive_integrations
Revises: bd2ba1a5c466
Create Date: 2026-09-02
"""

from alembic import op
import sqlalchemy as sa


revision = "20260902_hive_integrations"
down_revision = "bd2ba1a5c466"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hive_identity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("tenant_settings_id", sa.Integer(), nullable=True),
        sa.Column("hive_user_id", sa.String(length=64), nullable=False),
        sa.Column("hive_tenant_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_settings_id"], ["tenant_settings.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_settings_id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index(op.f("ix_hive_identity_hive_tenant_id"), "hive_identity", ["hive_tenant_id"], unique=False)
    op.create_index(op.f("ix_hive_identity_hive_user_id"), "hive_identity", ["hive_user_id"], unique=True)
    op.create_index(op.f("ix_hive_identity_user_id"), "hive_identity", ["user_id"], unique=True)

    op.create_table(
        "app_integration",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_module_id", sa.Integer(), nullable=False),
        sa.Column("service_key", sa.String(length=100), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("sso_path", sa.String(length=255), nullable=False),
        sa.Column("sso_audience", sa.String(length=150), nullable=True),
        sa.Column("event_token_env", sa.String(length=150), nullable=True),
        sa.Column("summary_path", sa.String(length=255), nullable=True),
        sa.Column("health_path", sa.String(length=255), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["app_module_id"], ["app_module.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_module_id"),
        sa.UniqueConstraint("service_key"),
    )
    op.create_index(op.f("ix_app_integration_app_module_id"), "app_integration", ["app_module_id"], unique=True)
    op.create_index(op.f("ix_app_integration_service_key"), "app_integration", ["service_key"], unique=True)

    op.create_table(
        "integration_event",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("app_integration_id", sa.Integer(), nullable=False),
        sa.Column("consultant_id", sa.Integer(), nullable=True),
        sa.Column("hive_tenant_id", sa.String(length=64), nullable=True),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=30), nullable=False),
        sa.Column("target_url", sa.String(length=1000), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["app_integration_id"], ["app_integration.id"]),
        sa.ForeignKeyConstraint(["consultant_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("app_integration_id", "external_event_id", name="uq_integration_event_external_id"),
    )
    op.create_index(op.f("ix_integration_event_app_integration_id"), "integration_event", ["app_integration_id"], unique=False)
    op.create_index(op.f("ix_integration_event_consultant_id"), "integration_event", ["consultant_id"], unique=False)
    op.create_index(op.f("ix_integration_event_event_type"), "integration_event", ["event_type"], unique=False)
    op.create_index(op.f("ix_integration_event_hive_tenant_id"), "integration_event", ["hive_tenant_id"], unique=False)
    op.create_index(op.f("ix_integration_event_occurred_at"), "integration_event", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_integration_event_priority"), "integration_event", ["priority"], unique=False)
    op.create_index(op.f("ix_integration_event_status"), "integration_event", ["status"], unique=False)


def downgrade():
    op.drop_index(op.f("ix_integration_event_status"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_priority"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_occurred_at"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_hive_tenant_id"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_event_type"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_consultant_id"), table_name="integration_event")
    op.drop_index(op.f("ix_integration_event_app_integration_id"), table_name="integration_event")
    op.drop_table("integration_event")

    op.drop_index(op.f("ix_app_integration_service_key"), table_name="app_integration")
    op.drop_index(op.f("ix_app_integration_app_module_id"), table_name="app_integration")
    op.drop_table("app_integration")

    op.drop_index(op.f("ix_hive_identity_user_id"), table_name="hive_identity")
    op.drop_index(op.f("ix_hive_identity_hive_user_id"), table_name="hive_identity")
    op.drop_index(op.f("ix_hive_identity_hive_tenant_id"), table_name="hive_identity")
    op.drop_table("hive_identity")
