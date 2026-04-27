# gateway_client/__init__.py
"""
gateway_client — thin compatibility shim.

Previously this package contained a hand-rolled HTTP/WebSocket client
(client.py).  That file is deleted.  All gateway logic now lives in
adapter.py, which delegates entirely to the cipher_gateway SDK.

Public API re-exported here so the rest of the bot (main.py, etc.)
continues to import from `gateway_client` unchanged.
"""

from .adapter import (
    TonpoConnectionAdapter,
    GatewayManager,
    ExecutionProvider,
)

# GatewayConfig comes directly from the SDK — re-export so callers that do
#   from gateway_client import GatewayConfig
# or
#   from gateway_client.client import GatewayConfig
# both keep working without changes.
from tonpo import TonpoConfig

__all__ = [
    "TonpoConnectionAdapter",
    "GatewayManager",
    "ExecutionProvider",
    "TonpoConfig",
]
