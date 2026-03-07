# fx/core/exceptions.py
class FXSignalCopierError(Exception):
    """Base exception for all application errors"""
    pass

class ConfigurationError(FXSignalCopierError):
    """Raised when there's a configuration issue"""
    pass

class DatabaseError(FXSignalCopierError):
    """Raised for database-related errors"""
    pass

class AuthenticationError(FXSignalCopierError):
    """Raised for authentication failures"""
    pass

class AuthorizationError(FXSignalCopierError):
    """Raised when user is not authorized"""
    pass

class ValidationError(FXSignalCopierError):
    """Raised for data validation failures"""
    pass

class TradeError(FXSignalCopierError):
    """Base class for trade-related errors"""
    pass

class SignalParseError(TradeError):
    """Raised when signal parsing fails"""
    pass

class InvalidSymbolError(TradeError):
    """Raised when symbol is invalid or not allowed"""
    pass

class RiskError(TradeError):
    """Raised for risk calculation errors"""
    pass

class InsufficientBalanceError(TradeError):
    """Raised when account balance is insufficient"""
    pass

class PositionSizeError(TradeError):
    """Raised when position size is invalid"""
    pass

class ConnectionError(FXSignalCopierError):
    """Raised for connection issues"""
    pass

class MT5ConnectionError(ConnectionError):
    """Raised when MT5 connection fails"""
    pass

class MetaAPIError(ConnectionError):
    """Raised when MetaAPI connection fails"""
    pass

class RateLimitError(FXSignalCopierError):
    """Raised when rate limit is exceeded"""
    pass

class SubscriptionError(FXSignalCopierError):
    """Raised for subscription-related issues"""
    pass

class FeatureNotAvailableError(SubscriptionError):
    """Raised when feature is not available in current plan"""
    pass

class LimitExceededError(SubscriptionError):
    """Raised when usage limit is exceeded"""
    pass

class NotificationError(FXSignalCopierError):
    """Raised for notification failures"""
    pass

class CacheError(FXSignalCopierError):
    """Raised for caching issues"""
    pass

class QueueError(FXSignalCopierError):
    """Raised for queue/task issues"""
    pass

class MonitoringError(FXSignalCopierError):
    """Raised for monitoring failures"""
    pass

class APIError(FXSignalCopierError):
    """Raised for API-related errors"""
    pass

class WebhookError(FXSignalCopierError):
    """Raised for webhook processing errors"""
    pass