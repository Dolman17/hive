"""Add billing profile table

Revision ID: 20260529_add_billing_profile
Revises: 20260529_add_subscriptions
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = "20260529_add_billing_profile"
down_revision = "20260529_add_subscriptions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_profile",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=False),
        sa.Column("billing_email", sa.String(length=255), nullable=True),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_price_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_checkout_session_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_end", sa.DateTime(), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscription.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("subscription_id"),
    )


def downgrade():
    op.drop_table("billing_profile")
