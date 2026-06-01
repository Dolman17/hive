"""add consultant access requests

Revision ID: 20260601_consultant_access_requests
Revises: 20260529_enquiry_timeline
"""
from alembic import op
import sqlalchemy as sa


revision = "20260601_consultant_access_requests"
down_revision = "20260529_enquiry_timeline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consultant_access_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("consultancy_name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(100), nullable=True),
        sa.Column("specialisms", sa.Text(), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("remote_work", sa.String(100), nullable=True),
        sa.Column("interested_in", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="new"),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("created_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["created_user_id"], ["user.id"]),
    )
    op.create_index("ix_consultant_access_request_contact_email", "consultant_access_request", ["contact_email"])
    op.create_index("ix_consultant_access_request_status", "consultant_access_request", ["status"])


def downgrade():
    op.drop_index("ix_consultant_access_request_status", table_name="consultant_access_request")
    op.drop_index("ix_consultant_access_request_contact_email", table_name="consultant_access_request")
    op.drop_table("consultant_access_request")
