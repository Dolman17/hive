"""notifications

Revision ID: 20260529_notifications
Revises: 20260529_enquiry_timeline
"""
from alembic import op
import sqlalchemy as sa

revision = "20260529_notifications"
down_revision = "20260529_enquiry_timeline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("link_url", sa.String(500), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("read_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["recipient_user_id"], ["user.id"]),
    )


def downgrade():
    op.drop_table("notification")
