# fx/config/constants.py
from enum import Enum, IntEnum
from typing import Dict, List, Any

# Order Types
class OrderType(str, Enum):
    """MT5 Order Types"""
    BUY = "Buy"
    SELL = "Sell"
    BUY_LIMIT = "Buy Limit"
    SELL_LIMIT = "Sell Limit"
    BUY_STOP = "Buy Stop"
    SELL_STOP = "Sell Stop"
    
    @classmethod
    def list(cls):
        return [e.value for e in cls]


# Conversation States
class ConversationState(IntEnum):
    """Telegram conversation states"""
    # Registration states
    REG_ACCOUNT = 0
    REG_PASSWORD = 1
    REG_SERVER = 2
    REG_CONFIRM = 3
    REG_RISK = 4
    
    # Trading states
    TRADE_ENTRY = 10
    TRADE_CONFIRM = 11
    TRADE_ADJUST = 12
    TRADE_EXECUTE = 13
    
    # Settings states
    SETTINGS_MAIN = 20
    SETTINGS_RISK = 21
    SETTINGS_NOTIFY = 22
    SETTINGS_SYMBOLS = 23
    SETTINGS_CONNECTION = 24
    SETTINGS_API = 25
    
    # Admin states
    ADMIN_MAIN = 30
    ADMIN_USER = 31
    ADMIN_BROADCAST = 32
    ADMIN_STATS = 33
    
    # Calculation states
    CALC_ENTRY = 40
    CALC_RESULT = 41


# Symbol Types
class SymbolType(str, Enum):
    """Symbol categories"""
    FOREX = "forex"
    COMMODITY = "commodity"
    INDEX = "index"
    CRYPTO = "crypto"
    
    FOREX_MAJOR = "forex_major"
    FOREX_MINOR = "forex_minor"
    FOREX_EXOTIC = "forex_exotic"


# Pip multipliers for different symbols
PIP_MULTIPLIERS: Dict[str, float] = {
    SymbolType.FOREX: 0.0001,
    SymbolType.FOREX_MAJOR: 0.0001,
    SymbolType.FOREX_MINOR: 0.0001,
    SymbolType.FOREX_EXOTIC: 0.01,  # For JPY pairs
    "XAUUSD": 0.1,  # Gold
    "XAGUSD": 0.001,  # Silver
    "BTCUSD": 1.0,  # Bitcoin
    "ETHUSD": 0.1,  # Ethereum
    "DEFAULT": 0.0001
}

# JPY pairs use different pip multiplier
JPY_SYMBOLS: List[str] = ['JPY']

# Trade execution modes
TRADE_MODES: Dict[str, str] = {
    'manual': 'Manual execution only',
    'semi_auto': 'Requires confirmation',
    'auto': 'Fully automatic'
}

# Subscription tiers
SUBSCRIPTION_TIERS: Dict[str, Dict[str, Any]] = {
    'free': {
        'name': 'Free',
        'price_monthly': 0,
        'price_yearly': 0,
        'max_trades_per_day': 10,
        'max_position_size': 1.0,
        'max_symbols': 30,
        'supports_multiple_tps': False,
        'supports_auto_trading': False,
        'supports_api': False,
        'support_priority': 'low',
        'max_connections': 1
    },
    'basic': {
        'name': 'Basic',
        'price_monthly': 9.99,
        'price_yearly': 99.99,
        'max_trades_per_day': 50,
        'max_position_size': 5.0,
        'max_symbols': 50,
        'supports_multiple_tps': True,
        'supports_auto_trading': False,
        'supports_api': False,
        'support_priority': 'normal',
        'max_connections': 2
    },
    'pro': {
        'name': 'Pro',
        'price_monthly': 29.99,
        'price_yearly': 299.99,
        'max_trades_per_day': 200,
        'max_position_size': 10.0,
        'max_symbols': 100,
        'supports_multiple_tps': True,
        'supports_auto_trading': True,
        'supports_api': True,
        'support_priority': 'high',
        'max_connections': 5
    },
    'enterprise': {
        'name': 'Enterprise',
        'price_monthly': 99.99,
        'price_yearly': 999.99,
        'max_trades_per_day': 1000,
        'max_position_size': 50.0,
        'max_symbols': 0,  # Unlimited
        'supports_multiple_tps': True,
        'supports_auto_trading': True,
        'supports_api': True,
        'support_priority': 'critical',
        'max_connections': 10
    }
}

# Notification types
NOTIFICATION_TYPES: Dict[str, str] = {
    'info': 'ℹ️ Information',
    'success': '✅ Success',
    'warning': '⚠️ Warning',
    'error': '❌ Error',
    'trade': '📈 Trade Update',
    'connection': '🔌 Connection Status',
    'subscription': '💎 Subscription Update',
    'admin': '👑 Admin Alert'
}

# Connection status
CONNECTION_STATUS: Dict[str, str] = {
    'connected': '✅ Connected',
    'disconnected': '❌ Disconnected',
    'connecting': '🔄 Connecting',
    'error': '⚠️ Error',
    'timeout': '⏰ Timeout'
}

# API Response Codes
API_CODES: Dict[int, str] = {
    200: 'Success',
    201: 'Created',
    400: 'Bad Request',
    401: 'Unauthorized',
    403: 'Forbidden',
    404: 'Not Found',
    429: 'Too Many Requests',
    500: 'Internal Server Error'
}

# Timeouts (in seconds)
TIMEOUTS: Dict[str, int] = {
    'connection': 30,
    'trade_execution': 60,
    'price_fetch': 10,
    'account_info': 15,
    'position_close': 30
}

# Rate limits (requests per minute)
RATE_LIMITS: Dict[str, int] = {
    'trade': 5,
    'calculate': 10,
    'balance': 30,
    'positions': 20,
    'history': 15,
    'settings': 20
}

# Pagination defaults
PAGINATION: Dict[str, int] = {
    'trades_per_page': 10,
    'users_per_page': 20,
    'notifications_per_page': 5
}

# Cache TTLs (in seconds)
CACHE_TTL: Dict[str, int] = {
    'user': 300,  # 5 minutes
    'settings': 600,  # 10 minutes
    'price': 5,  # 5 seconds
    'balance': 30,  # 30 seconds
    'positions': 10,  # 10 seconds
    'subscription': 3600,  # 1 hour
    'rate_limit': 60  # 1 minute
}

# Error messages
ERROR_MESSAGES: Dict[str, str] = {
    'not_registered': 'Please register first using /register',
    'invalid_signal': 'Invalid signal format. Use /help for examples',
    'connection_failed': 'Failed to connect to MT5. Check your credentials',
    'insufficient_balance': 'Insufficient balance for this trade',
    'rate_limited': 'Too many requests. Please wait {seconds} seconds',
    'maintenance': 'Bot is under maintenance. Please try again later',
    'unauthorized': 'You are not authorized to use this command',
    'subscription_expired': 'Your subscription has expired. Use /upgrade'
}

# Success messages
SUCCESS_MESSAGES: Dict[str, str] = {
    'registered': '✅ Successfully registered! Welcome to Tonpo Bot',
    'trade_executed': '✅ Trade executed successfully!',
    'settings_updated': '✅ Settings updated successfully',
    'connection_tested': '✅ Connection test successful'
}

# Regular expressions
REGEX_PATTERNS: Dict[str, str] = {
    'symbol': r'^[A-Z]{6}$',
    'price': r'^\d+\.?\d*$',
    'account_id': r'^\d{5,10}$',
    'server': r'^[A-Za-z0-9\-\.]+$',
    'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$',
    'phone': r'^\+?[1-9]\d{1,14}$',
    'uuid': r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
}