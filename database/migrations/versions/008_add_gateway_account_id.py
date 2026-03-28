# database/migrations/versions/008_add_gateway_account_id.py
"""add gateway_account_id

Revision ID: 008
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'

def upgrade():
    op.add_column('users', sa.Column('gateway_account_id', sa.String(64), nullable=True))
    op.create_index('ix_users_gateway_account_id', 'users', ['gateway_account_id'])

def downgrade():
    op.drop_index('ix_users_gateway_account_id', 'users')
    op.drop_column('users', 'gateway_account_id')