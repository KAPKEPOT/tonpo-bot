# fx/database/migrations/versions/007_add_payment_requests.py
"""add payment_requests table for crypto payments

Revision ID: 007
Revises: 006
Create Date: 2026-03-20 09:00:00.000000

Supports USDT (ERC-20) and BTC payments with unique amount identification.
"""
from alembic import op
import sqlalchemy as sa

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('payment_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('uuid', sa.String(36), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        
        # What they're paying for
        sa.Column('plan_tier', sa.String(20), nullable=False),
        sa.Column('billing_period', sa.String(10), nullable=False),  # 'monthly' or 'yearly'
        sa.Column('base_amount', sa.Numeric(12, 2), nullable=False),  # Plan price
        sa.Column('unique_amount', sa.Numeric(12, 4), nullable=False),  # Base + unique offset
        sa.Column('currency', sa.String(10), nullable=False),  # 'USDT' or 'BTC'
        
        # Wallet info
        sa.Column('wallet_address', sa.String(100), nullable=False),
        sa.Column('network', sa.String(20), nullable=False),  # 'ERC20', 'BTC'
        
        # Status tracking
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        # pending → confirmed → activated | expired | failed
        
        # Blockchain verification
        sa.Column('tx_hash', sa.String(100), nullable=True),
        sa.Column('confirmed_amount', sa.Numeric(12, 6), nullable=True),
        sa.Column('confirmations', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('block_number', sa.BigInteger(), nullable=True),
        
        # Timing
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(), nullable=True),
        sa.Column('activated_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        
        sa.PrimaryKeyConstraint('id'),
    )
    
    op.create_index('idx_payment_status', 'payment_requests', ['status'])
    op.create_index('idx_payment_user', 'payment_requests', ['user_id'])
    op.create_index('idx_payment_unique_amount', 'payment_requests', ['unique_amount', 'currency', 'status'])
    op.create_index('idx_payment_expires', 'payment_requests', ['expires_at', 'status'])


def downgrade():
    op.drop_table('payment_requests')
