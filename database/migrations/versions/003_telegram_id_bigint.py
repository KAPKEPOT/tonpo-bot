# fx/database/migrations/versions/003_telegram_id_bigint.py
"""alter telegram_id to bigint

Revision ID: 003
Revises: 002
Create Date: 2026-03-08 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the unique constraint and index first, alter the column, then recreate
    op.drop_index('idx_user_telegram_id', table_name='users')
    op.drop_constraint('users_telegram_id_key', 'users', type_='unique')

    op.alter_column(
        'users', 'telegram_id',
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        nullable=False
    )

    op.create_unique_constraint('users_telegram_id_key', 'users', ['telegram_id'])
    op.create_index('idx_user_telegram_id', 'users', ['telegram_id'])


def downgrade():
    op.drop_index('idx_user_telegram_id', table_name='users')
    op.drop_constraint('users_telegram_id_key', 'users', type_='unique')

    op.alter_column(
        'users', 'telegram_id',
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        nullable=False
    )

    op.create_unique_constraint('users_telegram_id_key', 'users', ['telegram_id'])
    op.create_index('idx_user_telegram_id', 'users', ['telegram_id'])
