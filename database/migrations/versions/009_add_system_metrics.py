# database/migrations/versions/009_add_system_metrics.py
"""add system_metrics

Revision ID: 009
"""
from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '008'

def upgrade():
    op.create_table('system_metrics',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('metric_name', sa.String(100), nullable=False),
        sa.Column('metric_value', sa.Float, nullable=False),
        sa.Column('tags', sa.JSON, nullable=True),
        sa.Column('created_at', sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index('ix_system_metrics_name', 'system_metrics', ['metric_name'])
    op.create_index('ix_system_metrics_created', 'system_metrics', ['created_at'])

def downgrade():
    op.drop_table('system_metrics')