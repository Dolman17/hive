"""directory enquiry timeline

Revision ID: 20260529_enquiry_timeline
Revises: 20260529_directory_enquiries
"""
from alembic import op
import sqlalchemy as sa

revision = "20260529_enquiry_timeline"
down_revision = "20260529_directory_enquiries"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "directory_enquiry_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enquiry_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("created_by_label", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["enquiry_id"], ["directory_enquiry.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"]),
    )


def downgrade():
    op.drop_table("directory_enquiry_event")
