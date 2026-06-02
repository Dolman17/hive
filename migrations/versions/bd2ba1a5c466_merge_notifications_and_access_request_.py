"""Merge notifications and access request heads

Revision ID: bd2ba1a5c466
Revises: 20260529_notifications, 20260601_access_reqs
Create Date: 2026-06-01 21:18:23.290624

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bd2ba1a5c466'
down_revision = ('20260529_notifications', '20260601_access_reqs')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
