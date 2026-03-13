# gateway_client/adapter.py
"""
Adapter to integrate gateway client with existing MetaAPI-based code
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from .client import GatewayClient, GatewayConfig, AccountInfo, Position, OrderResult
from config.settings import settings

logger = logging.getLogger(__name__)


class GatewayConnectionAdapter:
    """
    Adapter that mimics MetaAPI connection interface
    Allows drop-in replacement of MetaAPI with your gateway
    """
    
    def __init__(self, client: GatewayClient, user_id: str):
        self.client = client
        self.user_id = user_id
        self._connected = True
    
    async def get_account_information(self) -> Dict[str, Any]:
        """Get account info (MetaAPI compatible)"""
        account = await self.client.get_account_info()
        return {
            'login': account.login,
            'name': account.name,
            'balance': account.balance,
            'equity': account.equity,
            'margin': account.margin,
            'free_margin': account.free_margin,
            'margin_level': account.margin / account.equity * 100 if account.equity > 0 else 0,
            'currency': account.currency,
            'server': account.server,
            'leverage': account.leverage,
            'profit': account.profit
        }
    
    async def get_positions(self) -> List[Dict[str, Any]]:
        """Get positions (MetaAPI compatible)"""
        positions = await self.client.get_positions()
        return [{
            'id': p.ticket,
            'symbol': p.symbol,
            'type': p.side,
            'volume': p.volume,
            'openPrice': p.open_price,
            'currentPrice': p.current_price,
            'stopLoss': p.sl,
            'takeProfit': p.tp,
            'profit': p.profit,
            'swap': p.swap,
            'commission': p.commission,
            'comment': p.comment
        } for p in positions]
    
    async def create_market_buy_order(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create market buy order (MetaAPI compatible)"""
        result = await self.client.place_order(
            symbol=symbol,
            side='buy',
            order_type='market',
            volume=volume,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    async def create_market_sell_order(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create market sell order (MetaAPI compatible)"""
        result = await self.client.place_order(
            symbol=symbol,
            side='sell',
            order_type='market',
            volume=volume,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    async def create_limit_buy_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create limit buy order (MetaAPI compatible)"""
        result = await self.client.place_order(
            symbol=symbol,
            side='buy',
            order_type='limit',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    async def close_position(self, position_id: str) -> bool:
        """Close position (MetaAPI compatible)"""
        result = await self.client.close_order(ticket=int(position_id))
        return result.success
    
    async def modify_position(
        self,
        position_id: str,
        sl: Optional[float] = None,
        tp: Optional[float] = None
    ) -> bool:
        """Modify position (MetaAPI compatible)"""
        result = await self.client.modify_order(
            ticket=int(position_id),
            sl=sl,
            tp=tp
        )
        return result.success
    
    async def get_symbol_price(self, symbol: str) -> Dict[str, float]:
        """Get current price (fallback - could use WebSocket cache)"""
        # This would need a price cache from WebSocket
        # For now, return dummy values
        return {'bid': 0, 'ask': 0}
    
    async def close(self):
        """Close connection"""
        self._connected = False


class GatewayManager:
    """
    Manages gateway connections for multiple users
    Replaces MT5ConnectionManager
    """
    
    def __init__(self, gateway_config: Optional[GatewayConfig] = None):
        self.gateway_config = gateway_config or GatewayConfig()
        self.client = GatewayClient(self.gateway_config)
        self.connections: Dict[int, GatewayConnectionAdapter] = {}
        self.user_api_keys: Dict[int, str] = {}
        self.user_gateway_ids: Dict[int, str] = {}
        
        # Readiness tracking
        self._ready = asyncio.Event()
        self._ready_error: Optional[str] = None
        
        logger.info("Gateway manager initialized")
        
        gateway_manager = GatewayManager(GatewayConfig(
            host=settings.GATEWAY_HOST,
            port=settings.GATEWAY_PORT,
            use_ssl=settings.GATEWAY_USE_SSL,
            api_key_header=settings.GATEWAY_API_KEY_HEADER,
            connect_timeout=settings.GATEWAY_CONNECT_TIMEOUT,
            request_timeout=settings.GATEWAY_REQUEST_TIMEOUT
        ))
    
    async def start(self):
        """Start the gateway manager"""
        logger.info("Starting Gateway Manager...")
        await self.client.start()
        
        # Check connection to gateway
        try:
            healthy = await self.client.health_check()
            if healthy:
                self._ready.set()
                logger.info("Gateway manager ready")
            else:
                self._ready_error = "Gateway health check failed"
                logger.error(self._ready_error)
        except Exception as e:
            self._ready_error = f"Failed to connect to gateway: {e}"
            logger.error(self._ready_error)
    
    async def stop(self):
        """Stop the gateway manager"""
        logger.info("Stopping Gateway Manager...")
        
        # Close all user connections
        for user_id in list(self.connections.keys()):
            try:
                await self.connections[user_id].close()
            except:
                pass
        
        await self.client.stop()
        logger.info("Gateway manager stopped")
    
    async def wait_until_ready(self, timeout: float = 30.0):
        """Wait until manager is ready"""
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True, None
        except asyncio.TimeoutError:
            return False, self._ready_error or "Timeout"
    
    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()
    
    async def register_user(
        self,
        telegram_id: int,
        mt5_account: str,
        mt5_password: str,
        mt5_server: str
    ) -> tuple[bool, str]:
        """
        Register a user with the gateway
        Called during registration
        """
        try:
            # Create user in gateway
            user_info = await self.client.create_user()
            
            # Store gateway user ID
            self.user_gateway_ids[telegram_id] = user_info.user_id
            
            # Connect MT5 account
            result = await self.client.connect_mt5(
                mt5_login=mt5_account,
                mt5_password=mt5_password,
                server=mt5_server,
                user_id=user_info.user_id
            )
            
            # Store API key
            # Note: The gateway might return API key in connect response
            # For now, we'll store the token
            self.user_api_keys[telegram_id] = user_info.token
            self.client.set_api_key(user_info.token)
            
            logger.info(f"User {telegram_id} registered with gateway")
            return True, "Connected successfully"
            
        except Exception as e:
            logger.error(f"Gateway registration failed for user {telegram_id}: {e}")
            return False, str(e)
    
    async def get_connection(self, telegram_id: int) -> GatewayConnectionAdapter:
        """
        Get or create a connection for a user
        """
        # Check if we already have a connection
        if telegram_id in self.connections:
            return self.connections[telegram_id]
        
        # Check if user is registered
        if telegram_id not in self.user_api_keys:
            raise ValueError(f"User {telegram_id} not registered with gateway")
        
        # Set API key for client
        self.client.set_api_key(self.user_api_keys[telegram_id])
        
        # Create connection adapter
        connection = GatewayConnectionAdapter(
            self.client,
            self.user_gateway_ids.get(telegram_id, "")
        )
        
        self.connections[telegram_id] = connection
        logger.info(f"Created gateway connection for user {telegram_id}")
        
        return connection
    
    async def close_connection(self, telegram_id: int):
        """Close a user's connection"""
        if telegram_id in self.connections:
            await self.connections[telegram_id].close()
            del self.connections[telegram_id]
            logger.info(f"Closed connection for user {telegram_id}")
    
    def get_connection_status(self, telegram_id: int) -> bool:
        """Get connection status"""
        return telegram_id in self.connections


class ExecutionProvider:
    """
    Unified execution provider that can switch between MetaAPI and Gateway
    """
    
    def __init__(self, use_gateway: bool = True):
        self.use_gateway = use_gateway
        self.gateway_manager: Optional[GatewayManager] = None
        self.metaapi_manager = None  # Keep original MetaAPI manager for fallback
        self.user_preferences: Dict[int, bool] = {}  # user_id -> use_gateway
    
    async def initialize(self, gateway_config: Optional[GatewayConfig] = None):
        """Initialize providers"""
        if self.use_gateway:
            self.gateway_manager = GatewayManager(gateway_config)
            await self.gateway_manager.start()
    
    async def shutdown(self):
        """Shutdown providers"""
        if self.gateway_manager:
            await self.gateway_manager.stop()
    
    def set_user_preference(self, user_id: int, use_gateway: bool):
        """Set user's preferred provider"""
        self.user_preferences[user_id] = use_gateway
    
    async def get_connection(self, user_id: int):
        """
        Get appropriate connection for user
        """
        # Check user preference
        use_gateway = self.user_preferences.get(user_id, self.use_gateway)
        
        if use_gateway and self.gateway_manager:
            try:
                return await self.gateway_manager.get_connection(user_id)
            except Exception as e:
                logger.warning(f"Gateway connection failed for user {user_id}, falling back to MetaAPI: {e}")
                # Fall back to MetaAPI
                return await self._get_metaapi_connection(user_id)
        else:
            return await self._get_metaapi_connection(user_id)
    
    async def _get_metaapi_connection(self, user_id: int):
        """Get MetaAPI connection (placeholder)"""
        if not self.metaapi_manager:
            raise RuntimeError("MetaAPI manager not initialized")
        return await self.metaapi_manager.get_connection(user_id)
    
    async def register_user(
        self,
        telegram_id: int,
        mt5_account: str,
        mt5_password: str,
        mt5_server: str
    ) -> tuple[bool, str]:
        """
        Register user with both providers
        """
        success_gateway = False
        success_metaapi = False
        
        # Register with gateway
        if self.gateway_manager:
            try:
                success, msg = await self.gateway_manager.register_user(
                    telegram_id, mt5_account, mt5_password, mt5_server
                )
                if success:
                    success_gateway = True
                logger.info(f"Gateway registration: {msg}")
            except Exception as e:
                logger.error(f"Gateway registration failed: {e}")
        
        # Register with MetaAPI
        # ... (call original registration)
        
        return success_gateway or success_metaapi, "Registration processed"