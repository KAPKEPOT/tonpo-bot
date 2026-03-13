# fx/gateway_client/__init__.py
"""
Gateway client package for Cipher MT5 Gateway integration
"""

from .client import (
    GatewayClient, GatewayConfig, GatewayError,
    AuthenticationError, ConnectionError, OrderError,
    SubscriptionError, AccountInfo, Position, OrderResult,
    Quote, Tick, Candle, OrderType, OrderSide
)

from .adapter import (
    GatewayConnectionAdapter, GatewayManager, ExecutionProvider
)

__all__ = [
    # Client
    'GatewayClient',
    'GatewayConfig',
    'GatewayError',
    'AuthenticationError',
    'ConnectionError',
    'OrderError',
    'SubscriptionError',
    
    # Data classes
    'AccountInfo',
    'Position',
    'OrderResult',
    'Quote',
    'Tick',
    'Candle',
    
    # Enums
    'OrderType',
    'OrderSide',
    
    # Adapters
    'GatewayConnectionAdapter',
    'GatewayManager',
    'ExecutionProvider'
]