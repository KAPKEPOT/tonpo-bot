# gateway_client/adapter.py
import asyncio
import logging
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

from .client import GatewayClient, GatewayConfig, AccountInfo, Position, OrderResult
from config.settings import settings

logger = logging.getLogger(__name__)


class GatewayConnectionAdapter:
    def __init__(self, client: GatewayClient, user_id: str):
        self.client = client
        self.user_id = user_id
        self._connected = True
    
    async def get_account_information(self) -> Dict[str, Any]:
        """Get account info """
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
        """Get positions"""
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
    
    # ==================== Market Orders ====================
    
    async def create_market_buy_order(
        self,
        symbol: str,
        volume: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create market buy order """
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
        """Create market sell order"""
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
    
    # Limit Orders 
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
        """Create limit buy order """
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
    
    async def create_limit_sell_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create limit sell order """
        result = await self.client.place_order(
            symbol=symbol,
            side='sell',
            order_type='limit',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    # Stop Orders 
    async def create_stop_buy_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create stop buy order """
        result = await self.client.place_order(
            symbol=symbol,
            side='buy',
            order_type='stop',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    async def create_stop_sell_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create stop sell order """
        result = await self.client.place_order(
            symbol=symbol,
            side='sell',
            order_type='stop',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    # Stop-Limit Orders 
    async def create_stop_limit_buy_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create stop-limit buy order"""
        result = await self.client.place_order(
            symbol=symbol,
            side='buy',
            order_type='stop_limit',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    async def create_stop_limit_sell_order(
        self,
        symbol: str,
        volume: float,
        price: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create stop-limit sell order"""
        result = await self.client.place_order(
            symbol=symbol,
            side='sell',
            order_type='stop_limit',
            volume=volume,
            price=price,
            sl=sl,
            tp=tp,
            comment=comment,
            magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}
    
    # Position Management  
    async def close_position(self, position_id: str) -> bool:
        """Close position"""
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
    
    # Market Data 
    
    async def get_symbol_price(self, symbol: str) -> Dict[str, float]:
        """
        Get current bid/ask price for a symbol.
        Calls GET /api/symbols/:symbol on the gateway, which returns
        symbol info including current spread/price data.
        """
        try:
            # Use the gateway's symbol info endpoint to get price data
            info = await self.client.get_symbol_info(symbol)
            if info and isinstance(info, dict):
                info_data = info.get('info', info)
                bid = float(info_data.get('bid', 0))
                ask = float(info_data.get('ask', 0))
                
                # If bid/ask not directly in symbol info, calculate from spread
                if bid == 0 and ask == 0:
                    # Some gateway implementations return price via tick data
                    # Fall back to getting last tick via WebSocket price cache
                    cached = self._get_cached_price(symbol)
                    if cached:
                        return cached
                
                return {'bid': bid, 'ask': ask}
        except Exception as e:
            logger.warning(f"Failed to get price for {symbol} from gateway: {e}")
        
        # Final fallback — try WebSocket price cache
        cached = self._get_cached_price(symbol)
        if cached:
            return cached
        
        raise RuntimeError(f"Unable to get price for {symbol} — no data available")
    
    def _get_cached_price(self, symbol: str) -> Optional[Dict[str, float]]:
        """Check if client has cached price from WebSocket tick stream"""
        if hasattr(self.client, '_price_cache') and symbol in self.client._price_cache:
            cached = self.client._price_cache[symbol]
            return {'bid': cached['bid'], 'ask': cached['ask']}
        return None
    
    async def close(self):
        """Close connection and its dedicated HTTP client"""
        self._connected = False
        if self.client:
            await self.client.stop()


class GatewayManager:
    """
    Manages gateway connections for multiple users.
    """
    
    def __init__(self, gateway_config: Optional[GatewayConfig] = None):
        self.gateway_config = gateway_config or GatewayConfig()
        
        # Shared client used ONLY for health checks and user creation (no auth needed)
        self.admin_client = GatewayClient(self.gateway_config)
        
        # Per-user clients — each has their own API key set
        self.user_clients: Dict[int, GatewayClient] = {}
        self.connections: Dict[int, GatewayConnectionAdapter] = {}
        self.user_api_keys: Dict[int, str] = {}
        self.user_gateway_ids: Dict[int, str] = {}
        
        # Readiness tracking
        self._ready = asyncio.Event()
        self._ready_error: Optional[str] = None
        
        logger.info("Gateway manager initialized")
        
    async def start(self):
        """Start the gateway manager"""
        logger.info("Starting Gateway Manager...")
        await self.admin_client.start()
        
        # Check connection to gateway
        try:
            healthy = await self.admin_client.health_check()
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
        
        # Close all per-user clients
        for user_id, client in list(self.user_clients.items()):
            try:
                await client.stop()
            except Exception:
                pass
        self.user_clients.clear()
        self.connections.clear()
        
        # Close admin client
        await self.admin_client.stop()
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
    
    async def _create_user_client(self, api_key: str) -> GatewayClient:
        """Create a dedicated GatewayClient for a specific user"""
        client = GatewayClient(self.gateway_config)
        await client.start()
        client.set_api_key(api_key)
        return client
    
    async def register_user(
        self,
        telegram_id: int,
        mt5_account: str,
        mt5_password: str,
        mt5_server: str
    ) -> tuple:
        """
        Register a user with the gateway.
        Called during /register flow.
        """
        try:
            try:
            	from services.subscription import SubscriptionService
            	from database.database import db_manager
            	sub_service = SubscriptionService(db_manager.get_session())
            	plan = sub_service.get_user_plan(telegram_id)
            	current_connections = len([uid for uid in self.user_clients if uid == telegram_id])
            	if plan and plan.max_connections and current_connections >= plan.max_connections:
            		return False, f"Connection limit reached ({plan.max_connections} for {plan.tier} plan)", {}
            except Exception as e:
            	logger.warning(f"Could not check connection limit: {e}")
            	
            # Create user in gateway (uses admin client, no auth needed)
            user_info = await self.admin_client.create_user()
            
            # Store gateway user ID and API key
            api_key = user_info.api_key or user_info.token
            self.user_gateway_ids[telegram_id] = user_info.user_id
            self.user_api_keys[telegram_id] = api_key
            
            # Create a dedicated client for this user
            user_client = await self._create_user_client(api_key)
            self.user_clients[telegram_id] = user_client
            
            # Connect MT5 account using the user's own client
            result = await user_client.connect_mt5(
                mt5_login=mt5_account,
                mt5_password=mt5_password,
                server=mt5_server,
                user_id=user_info.user_id
            )
            
            logger.info(f"User {telegram_id} registered with gateway (gw_id={user_info.user_id})")
            return True, "Connected successfully", {
                'gateway_user_id': user_info.user_id,
                'gateway_api_key': api_key
            }
            
        except Exception as e:
            logger.error(f"Gateway registration failed for user {telegram_id}: {e}")
            # Clean up on failure
            self.user_clients.pop(telegram_id, None)
            self.user_api_keys.pop(telegram_id, None)
            self.user_gateway_ids.pop(telegram_id, None)
            return False, str(e)
    
    async def get_connection(self, telegram_id: int) -> GatewayConnectionAdapter:
        """
        Get or create a connection adapter for a user.
        Each user gets a dedicated GatewayClient, eliminating the
        API key race condition.
        """
        # Return existing connection
        if telegram_id in self.connections:
            return self.connections[telegram_id]
        
        # Check if user is registered
        if telegram_id not in self.user_api_keys:
            raise ValueError(f"User {telegram_id} not registered with gateway")
        
        # Create dedicated client if needed (e.g. after bot restart with loaded keys)
        if telegram_id not in self.user_clients:
            api_key = self.user_api_keys[telegram_id]
            self.user_clients[telegram_id] = await self._create_user_client(api_key)
        
        # Create connection adapter with the user's own client
        connection = GatewayConnectionAdapter(
            self.user_clients[telegram_id],
            self.user_gateway_ids.get(telegram_id, "")
        )
        
        self.connections[telegram_id] = connection
        logger.info(f"Created gateway connection for user {telegram_id}")
        
        return connection
    
    async def close_connection(self, telegram_id: int):
        """Close a user's connection and its dedicated client"""
        if telegram_id in self.connections:
            await self.connections[telegram_id].close()
            del self.connections[telegram_id]
        
        if telegram_id in self.user_clients:
            await self.user_clients[telegram_id].stop()
            del self.user_clients[telegram_id]
        
        logger.info(f"Closed connection for user {telegram_id}")
    
    def get_connection_status(self, telegram_id: int) -> bool:
        """Get connection status"""
        return telegram_id in self.connections
    
    def load_user_credentials(self, telegram_id: int, api_key: str, gateway_user_id: str):
        """
        Load stored credentials (called on startup from database).
        The actual client is created lazily in get_connection().
        """
        self.user_api_keys[telegram_id] = api_key
        self.user_gateway_ids[telegram_id] = gateway_user_id


class ExecutionProvider:
    """
    Unified execution provider that can switch between MetaAPI and Gateway
    """
    
    def __init__(self, use_gateway: bool = True):
        self.use_gateway = use_gateway
        self.gateway_manager: Optional[GatewayManager] = None
    
    async def initialize(self, gateway_config: Optional[GatewayConfig] = None):
        """Initialize gateway"""
        self.gateway_manager = GatewayManager(gateway_config)
        await self.gateway_manager.start()
    
    async def shutdown(self):
        """Shutdown gateway"""
        if self.gateway_manager:
            await self.gateway_manager.stop()
    
    async def health_check(self) -> bool:
        """Check gateway health"""
        if self.gateway_manager and self.gateway_manager.admin_client:
            return await self.gateway_manager.admin_client.health_check()
        return False
    
    async def get_connection(self, user_id: int) -> GatewayConnectionAdapter:
        """Get gateway connection for user"""
        if not self.gateway_manager:
            raise RuntimeError("Gateway not initialized")
        return await self.gateway_manager.get_connection(user_id)
        
    async def register_user(
        self,
        telegram_id: int,
        mt5_account: str,
        mt5_password: str,
        mt5_server: str
    ) -> tuple:
        """
        Register user with gateway.
        Returns (success, message, credentials_dict).
        """
        if not self.gateway_manager:
            return False, "Gateway not initialized", {}

        try:
            return await self.gateway_manager.register_user(
                telegram_id, mt5_account, mt5_password, mt5_server
            )
        except Exception as e:
            logger.error(f"Registration failed for user {telegram_id}: {e}")
            return False, str(e), {}