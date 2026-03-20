# fx/database/migrations/versions/004_add_gateway_credentials.py
"""add gateway credentials to users

Revision ID: 004
Revises: 003
Create Date: 2026-03-20 07:30:00.000000

Stores CMG gateway user_id and api_key per user so they survive bot restarts.
"""
from alembic import op
import sqlalchemy as sa

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('gateway_user_id', sa.String(64), nullable=True))
    op.add_column('users', sa.Column('gateway_api_key', sa.Text(), nullable=True))
    
    # Index for fast lookup of gateway-registered users on startup
    op.create_index('idx_user_gateway', 'users', ['gateway_user_id'], unique=False)


def downgrade():
    op.drop_index('idx_user_gateway', table_name='users')
    op.drop_column('users', 'gateway_api_key')
    op.drop_column('users', 'gateway_user_id')
