"""directory enquiries

Revision ID: 20260529_directory_enquiries
Revises: 20260529_add_billing_profile
"""
from alembic import op
import sqlalchemy as sa


revision = "20260529_directory_enquiries"
down_revision = "20260529_add_billing_profile"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "directory_enquiry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("consultant_profile_id", sa.Integer(), sa.ForeignKey("consultant_profile.id"), nullable=False),
        sa.Column("assigned_consultant_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=False),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(100), nullable=True),
        sa.Column("support_needed", sa.Text(), nullable=True),
        sa.Column("urgency", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("consultant_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table("directory_enquiry")