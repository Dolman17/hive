"""Add explicit HIVE Client 360 record links.

Revision ID: 20260904_client_360_links
Revises: 20260903_pathly_config
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = "20260904_client_360_links"
down_revision = "20260903_pathly_config"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_record_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("consultant_id", sa.Integer(), nullable=False),
        sa.Column("hive_tenant_id", sa.String(length=64), nullable=False),
        sa.Column("external_client_id", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("source_record_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["consultant_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "consultant_id",
            "source_type",
            "source_record_id",
            name="uq_client_record_link_consultant_source",
        ),
    )
    op.create_index(
        "ix_client_record_link_consultant_id",
        "client_record_link",
        ["consultant_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_record_link_hive_tenant_id",
        "client_record_link",
        ["hive_tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_record_link_external_client_id",
        "client_record_link",
        ["external_client_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_record_link_source_type",
        "client_record_link",
        ["source_type"],
        unique=False,
    )
    op.create_index(
        "ix_client_record_link_source_record_id",
        "client_record_link",
        ["source_record_id"],
        unique=False,
    )
    op.create_index(
        "ix_client_record_link_consultant_client",
        "client_record_link",
        ["consultant_id", "external_client_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_client_record_link_consultant_client", table_name="client_record_link")
    op.drop_index("ix_client_record_link_source_record_id", table_name="client_record_link")
    op.drop_index("ix_client_record_link_source_type", table_name="client_record_link")
    op.drop_index("ix_client_record_link_external_client_id", table_name="client_record_link")
    op.drop_index("ix_client_record_link_hive_tenant_id", table_name="client_record_link")
    op.drop_index("ix_client_record_link_consultant_id", table_name="client_record_link")
    op.drop_table("client_record_link")
