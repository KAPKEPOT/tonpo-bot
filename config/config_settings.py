# fx/config/settings.py
import os
import json
from typing import List, Optional, Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """
    Application settings with validation
    """
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore'
    )
    
    # App Info
    APP_NAME: str = "FX Signal Copier"
    APP_VERSION: str = "2.0.0"
    APP_DESCRIPTION: str = "Telegram Bot for MetaTrader 5 Trading"
    DEBUG: bool = Field(False, validation_alias='DEBUG')
    
    # Gateway settings
    GATEWAY_HOST: str = Field(
        default="localhost",
        validation_alias="GATEWAY_HOST"
    )
    GATEWAY_PORT: int = Field(
        default=8080,
        validation_alias="GATEWAY_PORT",
        ge=1,
        le=65535
    )
    GATEWAY_USE_SSL: bool = Field(
        default=False,
        validation_alias="GATEWAY_USE_SSL"
    )
    GATEWAY_API_KEY_HEADER: str = Field(
        default="X-API-Key",
        validation_alias="GATEWAY_API_KEY_HEADER"
    )
    GATEWAY_CONNECT_TIMEOUT: float = Field(
        default=10.0,
        validation_alias="GATEWAY_CONNECT_TIMEOUT",
        gt=0
    )
    GATEWAY_REQUEST_TIMEOUT: float = Field(
        default=30.0,
        validation_alias="GATEWAY_REQUEST_TIMEOUT",
        gt=0
    )
    
    @property
    def gateway_config(self) -> 'GatewayConfig':
        """Get gateway configuration as a GatewayConfig object"""
        from gateway_client import GatewayConfig
        return GatewayConfig(
            host=self.GATEWAY_HOST,
            port=self.GATEWAY_PORT,
            use_ssl=self.GATEWAY_USE_SSL,
            api_key_header=self.GATEWAY_API_KEY_HEADER,
            connect_timeout=self.GATEWAY_CONNECT_TIMEOUT,
            request_timeout=self.GATEWAY_REQUEST_TIMEOUT,
        )
        
    # Telegram Configuration
    BOT_TOKEN: str = Field(..., validation_alias='BOT_TOKEN')
    BOT_USERNAME: Optional[str] = Field(None, validation_alias='BOT_USERNAME')
    ADMIN_USER_IDS: List[int] = Field(default=[], validation_alias='ADMIN_USER_IDS')
    USE_WEBHOOK: bool = Field(False, validation_alias='USE_WEBHOOK')
    WEBHOOK_URL: Optional[str] = Field(None, validation_alias='WEBHOOK_URL')
    WEBHOOK_PORT: int = Field(8443, validation_alias='WEBHOOK_PORT')
    WEBHOOK_HOST: str = Field("0.0.0.0", validation_alias='WEBHOOK_HOST')
    
    @field_validator('BOT_TOKEN')
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or ':' not in v:
            raise ValueError("Invalid BOT_TOKEN format")
        return v
    
    @field_validator('ADMIN_USER_IDS', mode='before')
    @classmethod
    def parse_admin_ids(cls, v):
        """Parse admin IDs from environment variable"""
        if v is None:
            return []
        if isinstance(v, str):
            # Strip inline comments before any parsing
            v = v.split('#')[0].strip()
            if not v:
            	return []
            # Try to parse as JSON first
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fall back to comma-separated parsing
                return [int(id.strip()) for id in v.split(',') if id.strip()]
        if isinstance(v, (list, tuple)):
            return [int(id) for id in v]
        return v
    
    # Database Configuration
    DATABASE_URL: str = Field(..., validation_alias='DATABASE_URL')
    DATABASE_POOL_SIZE: int = Field(20, validation_alias='DATABASE_POOL_SIZE')
    DATABASE_MAX_OVERFLOW: int = Field(10, validation_alias='DATABASE_MAX_OVERFLOW')
    DATABASE_POOL_TIMEOUT: int = Field(30, validation_alias='DATABASE_POOL_TIMEOUT')
    DATABASE_ECHO: bool = Field(False, validation_alias='DATABASE_ECHO')
    
    @field_validator('DATABASE_URL')
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        # Handle Heroku's postgres:// vs postgresql://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        return v
    
    # Redis Configuration
    REDIS_URL: Optional[str] = Field(None, validation_alias='REDIS_URL')
    REDIS_MAX_CONNECTIONS: int = Field(10, validation_alias='REDIS_MAX_CONNECTIONS')
    REDIS_SOCKET_TIMEOUT: int = Field(5, validation_alias='REDIS_SOCKET_TIMEOUT')
    
    # Security
    ENCRYPTION_KEY: Optional[str] = Field(None, validation_alias='ENCRYPTION_KEY')
    JWT_SECRET: str = Field(..., validation_alias='JWT_SECRET')
    JWT_ALGORITHM: str = Field("HS256", validation_alias='JWT_ALGORITHM')
    JWT_EXPIRY_HOURS: int = Field(24, validation_alias='JWT_EXPIRY_HOURS')
    CORS_ORIGINS: List[str] = Field(["*"], validation_alias='CORS_ORIGINS')
    
    @field_validator('ENCRYPTION_KEY')
    @classmethod
    def validate_encryption_key(cls, v):
        if not v:
            import base64
            import os
            # Generate a key for development
            v = base64.urlsafe_b64encode(os.urandom(32)).decode()
        return v
    
    # Trading Configuration
    DEFAULT_RISK_FACTOR: float = Field(0.01, validation_alias='DEFAULT_RISK_FACTOR')
    MAX_RISK_FACTOR: float = Field(0.05, validation_alias='MAX_RISK_FACTOR')
    MIN_RISK_FACTOR: float = Field(0.001, validation_alias='MIN_RISK_FACTOR')
    DEFAULT_MAX_POSITION_SIZE: float = Field(10.0, validation_alias='DEFAULT_MAX_POSITION_SIZE')
    ALLOWED_SYMBOLS: List[str] = Field([
        'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD',
        'CADCHF', 'CADJPY', 'CHFJPY', 'EURAUD', 'EURCAD',
        'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'EURUSD',
        'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD',
        'GBPUSD', 'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD',
        'USDCAD', 'USDCHF', 'USDJPY', 'XAGUSD', 'XAUUSD'
    ], validation_alias='ALLOWED_SYMBOLS')
    
    @field_validator('ALLOWED_SYMBOLS', mode='before')
    @classmethod
    def parse_symbols(cls, v):
        """Parse symbols from environment variable"""
        if v is None:
            return []
        if isinstance(v, str):
            # Try to parse as JSON first
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                # Fall back to comma-separated parsing
                return [s.strip().upper() for s in v.split(',') if s.strip()]
        if isinstance(v, (list, tuple)):
            return [str(s).upper() for s in v]
        return v
    
    # Rate Limiting
    RATE_LIMIT_TRADES: int = Field(5, validation_alias='RATE_LIMIT_TRADES')
    RATE_LIMIT_CALCULATIONS: int = Field(10, validation_alias='RATE_LIMIT_CALCULATIONS')
    RATE_LIMIT_BALANCE: int = Field(30, validation_alias='RATE_LIMIT_BALANCE')
    RATE_LIMIT_POSITIONS: int = Field(20, validation_alias='RATE_LIMIT_POSITIONS')
    
    # Subscription Plans (prices in USD)
    FREE_PLAN_MAX_TRADES: int = Field(10, validation_alias='FREE_PLAN_MAX_TRADES')
    FREE_PLAN_MAX_SIZE: float = Field(1.0, validation_alias='FREE_PLAN_MAX_SIZE')
    
    BASIC_PLAN_PRICE: float = Field(9.99, validation_alias='BASIC_PLAN_PRICE')
    BASIC_PLAN_MAX_TRADES: int = Field(50, validation_alias='BASIC_PLAN_MAX_TRADES')
    BASIC_PLAN_MAX_SIZE: float = Field(5.0, validation_alias='BASIC_PLAN_MAX_SIZE')
    
    PRO_PLAN_PRICE: float = Field(29.99, validation_alias='PRO_PLAN_PRICE')
    PRO_PLAN_MAX_TRADES: int = Field(200, validation_alias='PRO_PLAN_MAX_TRADES')
    PRO_PLAN_MAX_SIZE: float = Field(10.0, validation_alias='PRO_PLAN_MAX_SIZE')
    
    ENTERPRISE_PLAN_PRICE: float = Field(99.99, validation_alias='ENTERPRISE_PLAN_PRICE')
    ENTERPRISE_PLAN_MAX_TRADES: int = Field(1000, validation_alias='ENTERPRISE_PLAN_MAX_TRADES')
    ENTERPRISE_PLAN_MAX_SIZE: float = Field(50.0, validation_alias='ENTERPRISE_PLAN_MAX_SIZE')
    
    # Notification Settings
    NOTIFICATION_QUEUE_SIZE: int = Field(100, validation_alias='NOTIFICATION_QUEUE_SIZE')
    NOTIFICATION_BATCH_SIZE: int = Field(10, validation_alias='NOTIFICATION_BATCH_SIZE')
    NOTIFICATION_RETRY_ATTEMPTS: int = Field(3, validation_alias='NOTIFICATION_RETRY_ATTEMPTS')
    
    # Monitoring
    METRICS_ENABLED: bool = Field(True, validation_alias='METRICS_ENABLED')
    METRICS_PORT: int = Field(9090, validation_alias='METRICS_PORT')
    SENTRY_DSN: Optional[str] = Field(None, validation_alias='SENTRY_DSN')
    
    # Logging
    LOG_LEVEL: str = Field("INFO", validation_alias='LOG_LEVEL')
    LOG_FORMAT: str = Field(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        validation_alias='LOG_FORMAT'
    )
    LOG_FILE: Optional[str] = Field(None, validation_alias='LOG_FILE')
    LOG_MAX_BYTES: int = Field(10485760, validation_alias='LOG_MAX_BYTES')
    LOG_BACKUP_COUNT: int = Field(5, validation_alias='LOG_BACKUP_COUNT')
    
    # Feature Flags
    ENABLE_AUTO_TRADING: bool = Field(True, validation_alias='ENABLE_AUTO_TRADING')
    ENABLE_API_ACCESS: bool = Field(True, validation_alias='ENABLE_API_ACCESS')
    ENABLE_WEBHOOKS: bool = Field(False, validation_alias='ENABLE_WEBHOOKS')
    ENABLE_MULTIPLE_TPS: bool = Field(True, validation_alias='ENABLE_MULTIPLE_TPS')
    USE_GATEWAY: bool = Field(
        default=True,
        validation_alias='USE_GATEWAY'
    )
    GATEWAY_ONLY: bool = Field(
        default=False,
        validation_alias='GATEWAY_ONLY'
    )
    
    # Payment Processing (if using Stripe)
    STRIPE_API_KEY: Optional[str] = Field(None, validation_alias='STRIPE_API_KEY')
    STRIPE_WEBHOOK_SECRET: Optional[str] = Field(None, validation_alias='STRIPE_WEBHOOK_SECRET')

# Create global settings instance
settings = Settings()

# Validate critical settings
if not settings.ENCRYPTION_KEY:
    raise ValueError("ENCRYPTION_KEY must be set in production")