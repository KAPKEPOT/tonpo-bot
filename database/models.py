# fx/database/models.py
"""
Database models for FX Signal Copier
"""
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, 
    JSON, ForeignKey, Text, Index, UniqueConstraint, Numeric
)
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from datetime import datetime
import uuid
import re

from .database import Base


class User(Base):
    """User model - stores Telegram users and their MT5 credentials"""
    __tablename__ = 'users'
    
    # Primary key
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False)
    
    # Telegram info
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    telegram_username = Column(String(100), index=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    language_code = Column(String(10), default='en')
    
    # MetaTrader credentials (encrypted at application level)
    mt5_account_id = Column(String(50), nullable=False)
    mt5_password = Column(Text, nullable=False)  # Will be encrypted
    mt5_server = Column(String(100), nullable=False)
    metaapi_token = Column(Text, nullable=True)  # Optional personal token
    
    # Trading preferences
    default_risk_factor = Column(Float, default=0.01, nullable=False)
    max_position_size = Column(Float, default=10.0, nullable=False)
    allowed_symbols = Column(JSON, default=list)  # Empty list = all symbols
    blocked_symbols = Column(JSON, default=list)
    
    # Trade modes
    TRADE_MODES = ['manual', 'semi_auto', 'auto']
    trade_mode = Column(String(20), default='manual', nullable=False)
    
    # Account status
    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)
    is_banned = Column(Boolean, default=False, nullable=False)
    ban_reason = Column(String(200), nullable=True)
    
    # Subscription
    subscription_tier = Column(String(50), default='free', nullable=False)
    subscription_expiry = Column(DateTime, nullable=True)
    subscription_features = Column(JSON, default=dict)
    
    # MetaTrader connection status
    mt_connected = Column(Boolean, default=False)
    last_connected = Column(DateTime, nullable=True)
    connection_error = Column(String(200), nullable=True)
    connection_attempts = Column(Integer, default=0)
    
    # Statistics
    total_trades = Column(Integer, default=0)
    total_volume = Column(Float, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pips = Column(Float, default=0)
    
    # Rate limiting
    daily_trades = Column(Integer, default=0)
    last_trade_date = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())
    last_active = Column(DateTime, nullable=True)
    
    # Relationships
    trades = relationship("Trade", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    connection_logs = relationship("ConnectionLog", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_user_subscription', 'subscription_tier', 'subscription_expiry'),
        Index('idx_user_active', 'is_active', 'is_verified'),
    )
    
    @validates('telegram_username')
    def validate_username(self, key, value):
        """Validate telegram username format"""
        if value and not re.match(r'^[a-zA-Z0-9_]{5,32}$', value):
            raise ValueError("Invalid telegram username format")
        return value
    
    @validates('default_risk_factor')
    def validate_risk(self, key, value):
        """Validate risk factor is between 0.001 and 0.1 (0.1% to 10%)"""
        if not 0.001 <= value <= 0.1:
            raise ValueError("Risk factor must be between 0.001 and 0.1")
        return value
    
    @property
    def full_name(self) -> str:
        """Get user's full name"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.first_name or self.telegram_username or f"User_{self.telegram_id}"
    
    @property
    def is_premium(self) -> bool:
        """Check if user has premium subscription"""
        if not self.subscription_expiry:
            return False
        return self.subscription_expiry > datetime.utcnow() and self.subscription_tier != 'free'
    
    @property
    def win_rate(self) -> float:
        """Calculate user's win rate"""
        total_closed = self.winning_trades + self.losing_trades
        if total_closed == 0:
            return 0.0
        return (self.winning_trades / total_closed) * 100


class UserSettings(Base):
    """User-specific settings and preferences"""
    __tablename__ = 'user_settings'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), unique=True, nullable=False)
    
    # Notification preferences
    notify_on_trade = Column(Boolean, default=True)
    notify_on_error = Column(Boolean, default=True)
    notify_on_connection = Column(Boolean, default=True)
    notify_daily_report = Column(Boolean, default=False)
    notify_weekly_report = Column(Boolean, default=False)
    notification_hour = Column(Integer, default=9)  # Hour for daily report (UTC)
    
    # Risk overrides per symbol
    symbol_risk_overrides = Column(JSON, default=dict)  # {"XAUUSD": 0.005, "EURUSD": 0.01}
    
    # Auto TP/SL settings
    auto_tp_enabled = Column(Boolean, default=False)
    auto_tp_pips = Column(Integer, nullable=True)
    auto_sl_enabled = Column(Boolean, default=False)
    auto_sl_pips = Column(Integer, nullable=True)
    
    # Trade filters
    min_distance_from_price = Column(Integer, default=0)  # Minimum pips from current price
    max_spread = Column(Float, default=None, nullable=True)  # Maximum allowed spread
    
    # Display preferences
    decimal_places = Column(Integer, default=2)
    show_pips = Column(Boolean, default=True)
    
    # API access
    api_key = Column(String(64), unique=True, nullable=True)
    api_enabled = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="settings")
    
    @property
    def has_api_access(self) -> bool:
        """Check if user has API access enabled"""
        return self.api_enabled and self.api_key is not None


class Trade(Base):
    """Trade model - stores all executed trades"""
    __tablename__ = 'trades'
    
    id = Column(Integer, primary_key=True)
    uuid = Column(String(36), unique=True, default=lambda: str(uuid.uuid4()), nullable=False)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Trade details
    order_type = Column(String(20), nullable=False)  # Buy, Sell, Buy Limit, etc.
    symbol = Column(String(20), nullable=False, index=True)
    
    # Prices
    entry_price = Column(Numeric(20, 5), nullable=False)
    stop_loss = Column(Numeric(20, 5), nullable=False)
    take_profits = Column(JSON, nullable=False)  # Array of TP prices
    
    # Calculated values
    position_size = Column(Numeric(20, 2), nullable=False)
    risk_percentage = Column(Float, nullable=False)
    risk_amount = Column(Numeric(20, 2), nullable=False)  # In account currency
    potential_reward = Column(Numeric(20, 2), nullable=False)
    
    # Execution details
    mt_order_ids = Column(JSON, default=list)  # Array of MetaTrader order IDs
    STATUSES = ['pending', 'executed', 'partial', 'failed', 'cancelled']
    status = Column(String(20), default='pending', nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    
    # Signal source
    signal_text = Column(Text, nullable=False)
    signal_hash = Column(String(64), index=True)  # For duplicate detection
    signal_provider = Column(String(100), nullable=True)  # If from signal service
    
    # Performance (will be updated when trade closes)
    exit_price = Column(Numeric(20, 5), nullable=True)
    profit_loss = Column(Numeric(20, 2), nullable=True)
    profit_loss_pips = Column(Integer, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    # Timestamps
    executed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="trades")
    
    # Indexes
    __table_args__ = (
        Index('idx_trade_user_status', 'user_id', 'status'),
        Index('idx_trade_created', 'created_at'),
        Index('idx_trade_symbol', 'symbol', 'created_at'),
    )
    
    @property
    def risk_reward_ratio(self) -> float:
        """Calculate risk/reward ratio"""
        if self.risk_amount == 0:
            return 0
        return float(self.potential_reward) / float(self.risk_amount)
    
    @property
    def tp_count(self) -> int:
        """Number of take profit levels"""
        return len(self.take_profits) if self.take_profits else 0


class ConnectionLog(Base):
    """Logs of MetaTrader connection attempts"""
    __tablename__ = 'connection_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Connection details
    status = Column(String(20), nullable=False)  # success, failed, timeout
    error = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    
    # Connection info
    server = Column(String(100), nullable=True)
    account_type = Column(String(20), nullable=True)  # demo, real
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="connection_logs")
    
    __table_args__ = (
        Index('idx_connection_user_date', 'user_id', 'created_at'),
    )


class Notification(Base):
    """User notifications"""
    __tablename__ = 'notifications'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    
    # Notification content
    TYPES = ['info', 'success', 'warning', 'error']
    type = Column(String(20), default='info', nullable=False)
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    data = Column(JSON, default=dict)  # Additional data
    
    # Delivery
    is_read = Column(Boolean, default=False)
    is_delivered = Column(Boolean, default=False)
    delivered_at = Column(DateTime, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="notifications")
    
    __table_args__ = (
        Index('idx_notification_user_read', 'user_id', 'is_read'),
    )


class SubscriptionPlan(Base):
    """Available subscription plans"""
    __tablename__ = 'subscription_plans'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    tier = Column(String(20), unique=True, nullable=False)  # free, basic, pro, enterprise
    
    # Pricing
    price_monthly = Column(Numeric(10, 2), nullable=False)
    price_yearly = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default='USD')
    
    # Features
    max_trades_per_day = Column(Integer, default=10)
    max_position_size = Column(Float, default=1.0)
    max_symbols = Column(Integer, default=30)  # 0 = unlimited
    supports_multiple_tps = Column(Boolean, default=True)
    supports_auto_trading = Column(Boolean, default=False)
    supports_api = Column(Boolean, default=False)
    support_priority = Column(String(20), default='normal')
    
    # Limits
    max_connections = Column(Integer, default=1)
    rate_limit_per_second = Column(Integer, default=1)
    
    # Description
    description = Column(Text, nullable=True)
    features = Column(JSON, default=list)  # List of feature descriptions
    
    # Stripe integration
    stripe_price_id_monthly = Column(String(100), nullable=True)
    stripe_price_id_yearly = Column(String(100), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())
    
    @property
    def is_free(self) -> bool:
        """Check if this is a free plan"""
        return self.tier == 'free'


class ApiUsage(Base):
    """API usage tracking"""
    __tablename__ = 'api_usage'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    api_key = Column(String(64), nullable=False, index=True)
    
    # Usage
    endpoint = Column(String(100), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=False)
    
    # Request info
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index('idx_api_user_date', 'user_id', 'created_at'),
    )


class SystemMetric(Base):
    """System-wide metrics for monitoring"""
    __tablename__ = 'system_metrics'
    
    id = Column(Integer, primary_key=True)
    metric_name = Column(String(100), nullable=False, index=True)
    metric_value = Column(Float, nullable=False)
    
    # Tags for filtering
    tags = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    
    __table_args__ = (
        Index('idx_metric_name_date', 'metric_name', 'created_at'),
    )

class BotPersistenceStore(Base):
    """Key-value store for PTB conversation/user/chat/bot state (replaces pickle file)"""
    __tablename__ = 'bot_persistence_store'

    id    = Column(Integer, primary_key=True)
    key   = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
