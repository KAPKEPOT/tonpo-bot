# gateway_client/client.py
import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field, asdict
from enum import Enum
from core.exceptions import (
    GatewayError,
    AuthenticationError,
    GatewayConnectionError,
    OrderError,
    SubscriptionError,
)

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Order types matching gateway"""
    BUY = "Buy"
    SELL = "Sell"
    BUY_LIMIT = "Buy Limit"
    SELL_LIMIT = "Sell Limit"
    BUY_STOP = "Buy Stop"
    SELL_STOP = "Sell Stop"


class OrderSide(Enum):
    """Order side"""
    BUY = "buy"
    SELL = "sell"


@dataclass
class GatewayConfig:
    """Gateway connection configuration"""
    host: str = "localhost"
    port: int = 8080
    use_ssl: bool = False
    api_key_header: str = "X-API-Key"
    connect_timeout: float = 10.0
    request_timeout: float = 30.0
    ws_reconnect_delay: float = 5.0
    max_reconnect_attempts: int = 5
    
    @property
    def base_url(self) -> str:
        protocol = "https" if self.use_ssl else "http"
        return f"{protocol}://{self.host}:{self.port}"
    
    @property
    def ws_url(self) -> str:
        protocol = "wss" if self.use_ssl else "ws"
        return f"{protocol}://{self.host}:{self.port}/ws"


@dataclass
class UserInfo:
    """User information from gateway"""
    user_id: str
    token: str
    expires_in: int
    api_key: Optional[str] = None
    
    @property
    def is_expired(self) -> bool:
        """Check if token is expired"""
        # This would need actual expiration tracking
        return False


@dataclass
class AccountInfo:
    """MT5 account information"""
    login: int
    name: str
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    profit: float
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountInfo':
        return cls(
            login=data.get('login', 0),
            name=data.get('name', ''),
            server=data.get('server', ''),
            balance=float(data.get('balance', 0)),
            equity=float(data.get('equity', 0)),
            margin=float(data.get('margin', 0)),
            free_margin=float(data.get('free_margin', 0)),
            leverage=int(data.get('leverage', 0)),
            currency=data.get('currency', 'USD'),
            profit=float(data.get('profit', 0))
        )


@dataclass
class Position:
    """Open trading position"""
    ticket: int
    symbol: str
    side: str  # 'buy' or 'sell'
    volume: float
    open_price: float
    current_price: float
    profit: float
    swap: float
    commission: float
    sl: Optional[float] = None
    tp: Optional[float] = None
    open_time: Optional[int] = None
    comment: str = ""
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        return cls(
            ticket=data.get('ticket', 0),
            symbol=data.get('symbol', ''),
            side=data.get('side', 'buy'),
            volume=float(data.get('volume', 0)),
            open_price=float(data.get('openPrice', 0)),
            current_price=float(data.get('currentPrice', 0)),
            profit=float(data.get('profit', 0)),
            swap=float(data.get('swap', 0)),
            commission=float(data.get('commission', 0)),
            sl=float(data.get('sl')) if data.get('sl') else None,
            tp=float(data.get('tp')) if data.get('tp') else None,
            open_time=data.get('openTime'),
            comment=data.get('comment', '')
        )


@dataclass
class OrderResult:
    """Order execution result"""
    ticket: int
    success: bool
    error: Optional[str] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'OrderResult':
        return cls(
            ticket=data.get('ticket', 0),
            success=data.get('success', False),
            error=data.get('error')
        )


@dataclass
class Quote:
    """Real-time quote"""
    symbol: str
    bid: float
    ask: float
    time: int
    
    @property
    def spread(self) -> float:
        return self.ask - self.bid
    
    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass
class Tick:
    """Tick data"""
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    time: int


@dataclass
class Candle:
    """Candle data"""
    symbol: str
    timeframe: str
    time: int
    open: float
    high: float
    low: float
    close: float
    volume: int
    complete: bool

class GatewayClient:
    """
    Main client for Cipher MT5 Gateway
    Provides both REST and WebSocket interfaces
    """
    
    def __init__(self, config: Optional[GatewayConfig] = None):
        self.config = config or GatewayConfig()
        self.http_client: Optional[httpx.AsyncClient] = None
        self.ws_connection: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_task: Optional[asyncio.Task] = None
        self.api_key: Optional[str] = None
        self.user_info: Optional[UserInfo] = None
        
        # WebSocket callbacks
        self.tick_callbacks: Dict[str, List[Callable]] = {}
        self.quote_callbacks: Dict[str, List[Callable]] = {}
        self.candle_callbacks: Dict[str, List[Callable]] = {}
        self.position_callbacks: List[Callable] = []
        self.order_result_callbacks: List[Callable] = []
        self.account_callbacks: List[Callable] = []
        
        # Pending requests for WebSocket responses
        self._pending_requests: Dict[str, asyncio.Future] = {}
        
        # Connection state
        self._connected = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_attempts = 0
        
        # Price cache — populated by WebSocket tick stream, read by get_symbol_price
        self._price_cache: Dict[str, Dict[str, float]] = {}
        
        logger.info(f"Gateway client initialized for {self.config.base_url}")
    
    async def __aenter__(self):
        await self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
    
    async def start(self):
        """Start the client and establish connections"""
        self.http_client = httpx.AsyncClient(
            base_url=self.config.base_url,
            timeout=self.config.request_timeout,
            limits=httpx.Limits(max_keepalive_connections=10)
        )
        logger.info("Gateway client started")
    
    async def stop(self):
        """Stop the client and close all connections"""
        self._connected = False
        
        # Cancel reconnect task
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except:
                pass
        
        # Close WebSocket
        await self._close_websocket()
        
        # Close HTTP client
        if self.http_client:
            await self.http_client.aclose()
        
        logger.info("Gateway client stopped")
    
    async def _close_websocket(self):
        """Close WebSocket connection"""
        if self.ws_task and not self.ws_task.done():
            self.ws_task.cancel()
            try:
                await self.ws_task
            except:
                pass
        
        if self.ws_connection and not self.ws_connection.closed:
            await self.ws_connection.close()
            self.ws_connection = None
    
    # ==================== Authentication ====================
    
    async def create_user(self) -> UserInfo:
        """
        Create a new user in the gateway
        Returns user info with API key
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        try:
            response = await self.http_client.post("/api/users")
            response.raise_for_status()
            data = response.json()
            
            self.user_info = UserInfo(
                user_id=data.get('user_id', data.get('userId', '')),
                token=data.get('token', ''),
                expires_in=data.get('expires_in', data.get('expiresIn', 3600)),
                api_key=data.get('api_key', data.get('apiKey')),
            )
            
            # Auto-set the API key for subsequent requests
            if self.user_info.api_key:
                self.set_api_key(self.user_info.api_key)
            
            logger.info(f"Created gateway user: {self.user_info.user_id}")
            return self.user_info
            
        except httpx.HTTPStatusError as e:
            logger.error(f"Failed to create user: {e}")
            raise GatewayError(f"User creation failed: {e.response.text}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise GatewayError(str(e))
    
    def set_api_key(self, api_key: str):
        """Set API key for authentication"""
        self.api_key = api_key
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with authentication"""
        headers = {}
        if self.api_key:
            headers[self.config.api_key_header] = self.api_key
        return headers
    
    # ==================== REST API ====================
    
    async def connect_mt5(
        self,
        mt5_login: str,
        mt5_password: str,
        server: str,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Connect MT5 account to gateway
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        data = {
            "mt5Login": mt5_login,
            "mt5Password": mt5_password,
            "server": server
        }
        if user_id:
            data["userId"] = user_id
        
        try:
            response = await self.http_client.post(
                "/api/connect",
                json=data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            logger.error(f"MT5 connection failed: {e}")
            raise GatewayError(f"Connection failed: {e.response.text}")
    
    #  Account Lifecycle
    async def create_account(
        self,
        mt5_login: str,
        mt5_password: str,
        mt5_server: str,
        region: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a trading account on the gateway.
        Gateway encrypts credentials, provisions node, returns account_id + auth_token.
        This replaces the old connect_mt5() flow.
        """
        if not self.http_client:
            raise GatewayError("Client not started")

        data = {
            "mt5Login": mt5_login,
            "mt5Password": mt5_password,
            "mt5Server": mt5_server,
        }
        if region:
            data["region"] = region

        try:
            response = await self.http_client.post(
                "/api/accounts",
                json=data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Account created: {result.get('account_id')}")
            return result
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            raise GatewayError(f"Account creation failed: {e.response.text}")

    async def get_accounts(self) -> List[Dict[str, Any]]:
        """Get all trading accounts for the authenticated user"""
        if not self.http_client:
            raise GatewayError("Client not started")

        try:
            response = await self.http_client.get(
                "/api/accounts",
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return data.get("accounts", [])
        except httpx.HTTPStatusError as e:
            raise GatewayError(f"Failed to list accounts: {e.response.text}")

    async def get_account_status(self, account_id: str) -> Dict[str, Any]:
        """Get status of a specific trading account"""
        if not self.http_client:
            raise GatewayError("Client not started")

        try:
            response = await self.http_client.get(
                f"/api/accounts/{account_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise GatewayError(f"Account {account_id} not found")
            raise GatewayError(f"Failed to get account: {e.response.text}")

    async def delete_account(self, account_id: str) -> bool:
        """Delete a trading account and deprovision its node"""
        if not self.http_client:
            raise GatewayError("Client not started")

        try:
            response = await self.http_client.delete(
                f"/api/accounts/{account_id}",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            raise GatewayError(f"Failed to delete account: {e.response.text}")

    async def pause_account(self, account_id: str) -> bool:
        """Pause a trading account"""
        if not self.http_client:
            raise GatewayError("Client not started")

        try:
            response = await self.http_client.post(
                f"/api/accounts/{account_id}/pause",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            raise GatewayError(f"Failed to pause account: {e.response.text}")

    async def resume_account(self, account_id: str) -> bool:
        """Resume a paused trading account"""
        if not self.http_client:
            raise GatewayError("Client not started")

        try:
            response = await self.http_client.post(
                f"/api/accounts/{account_id}/resume",
                headers=self._get_headers()
            )
            response.raise_for_status()
            return True
        except httpx.HTTPStatusError as e:
            raise GatewayError(f"Failed to resume account: {e.response.text}")

    async def wait_for_account_active(
        self, account_id: str, timeout: int = 60, poll_interval: int = 3
    ) -> bool:
        """Poll account status until Active or timeout"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            try:
                status = await self.get_account_status(account_id)
                account_status = status.get("status", "")
                if account_status == "active":
                    return True
                if account_status in ("login_failed", "deleted"):
                    return False
            except GatewayError:
                pass
            await asyncio.sleep(poll_interval)
        return False
    
    async def get_account_info(self) -> AccountInfo:
        """
        Get MT5 account information
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        try:
            response = await self.http_client.get(
                "/api/account",
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return AccountInfo.from_dict(data['account'])
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            logger.error(f"Failed to get account info: {e}")
            raise GatewayError(f"Account info failed: {e.response.text}")
    
    async def get_positions(self) -> List[Position]:
        """
        Get open positions
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        try:
            response = await self.http_client.get(
                "/api/positions",
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return [Position.from_dict(p) for p in data.get('positions', [])]
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            logger.error(f"Failed to get positions: {e}")
            raise GatewayError(f"Get positions failed: {e.response.text}")
    
    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        volume: float,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: Optional[str] = None,
        magic: Optional[int] = None
    ) -> OrderResult:
        """
        Place an order
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        data = {
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "volume": volume
        }
        if price is not None:
            data["price"] = price
        if sl is not None:
            data["sl"] = sl
        if tp is not None:
            data["tp"] = tp
        if comment:
            data["comment"] = comment
        if magic:
            data["magic"] = magic
        
        try:
            response = await self.http_client.post(
                "/api/orders",
                json=data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return OrderResult.from_dict(data)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            error_data = e.response.json()
            raise OrderError(error_data.get('error', 'Order failed'))
    
    async def close_order(
        self,
        ticket: int,
        volume: Optional[float] = None
    ) -> OrderResult:
        """
        Close an order
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        data = {"ticket": ticket}
        if volume:
            data["volume"] = volume
        
        try:
            response = await self.http_client.post(
                "/api/orders/close",
                json=data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return OrderResult.from_dict(data)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            error_data = e.response.json()
            raise OrderError(error_data.get('error', 'Close order failed'))
    
    async def modify_order(
        self,
        ticket: int,
        price: Optional[float] = None,
        sl: Optional[float] = None,
        tp: Optional[float] = None
    ) -> OrderResult:
        """
        Modify an order
        """
        if not self.http_client:
            raise GatewayError("Client not started")
        
        data = {"ticket": ticket}
        if price is not None:
            data["price"] = price
        if sl is not None:
            data["sl"] = sl
        if tp is not None:
            data["tp"] = tp
        
        try:
            response = await self.http_client.post(
                "/api/orders/modify",
                json=data,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            return OrderResult.from_dict(data)
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise AuthenticationError("Invalid API key")
            error_data = e.response.json()
            raise OrderError(error_data.get('error', 'Modify order failed'))
    
    async def health_check(self) -> bool:
        """Check gateway health"""
        try:
            response = await self.http_client.get("/health")
            return response.status_code == 200
        except:
            return False
    
    # ==================== WebSocket ====================
    async def get_symbol_info(self, symbol: str) -> Dict[str, Any]:
    	"""Get symbol information from gateway. Returns symbol details including current price data."""
    	if not self.http_client:
    		raise GatewayError("Client not started")
    	
    	try:
    		response = await self.http_client.get(
        	    f"/api/symbols/{symbol}",
        	    headers=self._get_headers()
        	)
    		response.raise_for_status()
    		return response.json()
    	except httpx.HTTPStatusError as e:
    		if e.response.status_code == 401:
    			raise AuthenticationError("Invalid API key")
    		logger.error(f"Failed to get symbol info: {e}")
    		raise GatewayError(f"Symbol info failed: {e.response.text}")
    		
    async def connect_websocket(self):
        """Establish WebSocket connection for real-time data"""
        if self.ws_connection and not self.ws_connection.closed:
            return
        
        self._reconnect_attempts = 0
        await self._connect_websocket_with_retry()
    
    async def _connect_websocket_with_retry(self):
        """Connect WebSocket with retry logic"""
        while self._reconnect_attempts < self.config.max_reconnect_attempts:
            try:
                headers = self._get_headers()
                self.ws_connection = await websockets.connect(
                    self.config.ws_url,
                    extra_headers=headers,
                    timeout=self.config.connect_timeout
                )
                
                self._connected = True
                self._reconnect_attempts = 0
                logger.info("WebSocket connected")
                
                # Start listener task
                self.ws_task = asyncio.create_task(self._ws_listener())
                return
                
            except Exception as e:
                self._reconnect_attempts += 1
                logger.warning(
                    f"WebSocket connection failed (attempt {self._reconnect_attempts}): {e}"
                )
                
                if self._reconnect_attempts < self.config.max_reconnect_attempts:
                    await asyncio.sleep(self.config.ws_reconnect_delay)
                else:
                    logger.error("Max reconnection attempts reached")
                    raise GatewayConnectionError("Failed to connect WebSocket")
    
    async def _ws_listener(self):
        """Listen for WebSocket messages"""
        try:
            async for message in self.ws_connection:
                await self._handle_ws_message(message)
        except ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self._connected = False
            # Attempt to reconnect
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(
                    self._connect_websocket_with_retry()
                )
        except Exception as e:
            logger.error(f"WebSocket listener error: {e}")
            self._connected = False
    
    async def _handle_ws_message(self, message: str):
        """Handle incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'tick':
                await self._handle_tick(data)
            elif msg_type == 'quote':
                await self._handle_quote(data)
            elif msg_type == 'candle':
                await self._handle_candle(data)
            elif msg_type == 'position':
                await self._handle_position(data)
            elif msg_type == 'orderResult':
                await self._handle_order_result(data)
            elif msg_type == 'account':
                await self._handle_account(data)
            elif msg_type == 'pong':
                await self._handle_pong(data)
            elif msg_type == 'error':
                await self._handle_error(data)
            else:
                logger.debug(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON: {message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_tick(self, data: Dict[str, Any]):
        """Handle tick message"""
        tick = Tick(
            symbol=data['symbol'],
            bid=data['bid'],
            ask=data['ask'],
            last=data['last'],
            volume=data['volume'],
            time=data['time']
        )
        
        # Update price cache for get_symbol_price lookups
        self._price_cache[tick.symbol] = {
            'bid': tick.bid,
            'ask': tick.ask,
            'last': tick.last,
            'time': tick.time
        }
        
        # Call callbacks
        if tick.symbol in self.tick_callbacks:
            for callback in self.tick_callbacks[tick.symbol]:
                try:
                    await callback(tick) if asyncio.iscoroutinefunction(callback) else callback(tick)
                except Exception as e:
                    logger.error(f"Tick callback error: {e}")
    
    async def _handle_quote(self, data: Dict[str, Any]):
        """Handle quote message"""
        quote = Quote(
            symbol=data['symbol'],
            bid=data['bid'],
            ask=data['ask'],
            time=data['time']
        )
        
        if quote.symbol in self.quote_callbacks:
            for callback in self.quote_callbacks[quote.symbol]:
                try:
                    await callback(quote) if asyncio.iscoroutinefunction(callback) else callback(quote)
                except Exception as e:
                    logger.error(f"Quote callback error: {e}")
    
    async def _handle_candle(self, data: Dict[str, Any]):
        """Handle candle message"""
        candle = Candle(
            symbol=data['symbol'],
            timeframe=data['timeframe'],
            time=data['time'],
            open=data['open'],
            high=data['high'],
            low=data['low'],
            close=data['close'],
            volume=data['volume'],
            complete=data['complete']
        )
        
        key = f"{candle.symbol}:{candle.timeframe}"
        if key in self.candle_callbacks:
            for callback in self.candle_callbacks[key]:
                try:
                    await callback(candle) if asyncio.iscoroutinefunction(callback) else callback(candle)
                except Exception as e:
                    logger.error(f"Candle callback error: {e}")
    
    async def _handle_position(self, data: Dict[str, Any]):
        """Handle position update"""
        position = Position.from_dict(data)
        
        for callback in self.position_callbacks:
            try:
                await callback(position) if asyncio.iscoroutinefunction(callback) else callback(position)
            except Exception as e:
                logger.error(f"Position callback error: {e}")
    
    async def _handle_order_result(self, data: Dict[str, Any]):
        """Handle order result"""
        result = OrderResult.from_dict(data)
        
        for callback in self.order_result_callbacks:
            try:
                await callback(result) if asyncio.iscoroutinefunction(callback) else callback(result)
            except Exception as e:
                logger.error(f"Order result callback error: {e}")
    
    async def _handle_account(self, data: Dict[str, Any]):
        """Handle account update"""
        account = AccountInfo.from_dict(data)
        
        for callback in self.account_callbacks:
            try:
                await callback(account) if asyncio.iscoroutinefunction(callback) else callback(account)
            except Exception as e:
                logger.error(f"Account callback error: {e}")
    
    async def _handle_pong(self, data: Dict[str, Any]):
        """Handle pong response"""
        # Check if this is a response to a pending request
        request_id = data.get('request_id')
        if request_id and request_id in self._pending_requests:
            future = self._pending_requests.pop(request_id)
            future.set_result(data)
    
    async def _handle_error(self, data: Dict[str, Any]):
        """Handle error message"""
        code = data.get('code', 0)
        message = data.get('message', 'Unknown error')
        logger.error(f"Gateway error {code}: {message}")
    
    # ==================== WebSocket Commands ====================
    
    async def subscribe(
        self,
        symbols: List[str],
        timeframe: Optional[str] = None
    ) -> bool:
        """
        Subscribe to market data
        """
        if not self._connected or not self.ws_connection:
            await self.connect_websocket()
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        message = {
            "type": "subscribe",
            "symbols": symbols
        }
        if timeframe:
            message["timeframe"] = timeframe
        
        await self.ws_connection.send(json.dumps(message))
        
        try:
            # Wait for subscription confirmation
            response = await asyncio.wait_for(future, timeout=5.0)
            return response.get('type') == 'subscribed'
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise SubscriptionError("Subscription timeout")
    
    async def unsubscribe(self, symbols: List[str]) -> bool:
        """
        Unsubscribe from market data
        """
        if not self._connected or not self.ws_connection:
            return False
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        message = {
            "type": "unsubscribe",
            "symbols": symbols
        }
        await self.ws_connection.send(json.dumps(message))
        
        try:
            response = await asyncio.wait_for(future, timeout=5.0)
            return response.get('type') == 'unsubscribed'
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            return False
    
    async def get_positions_ws(self) -> List[Position]:
        """
        Get positions via WebSocket (async response)
        """
        if not self._connected or not self.ws_connection:
            await self.connect_websocket()
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        await self.ws_connection.send(json.dumps({
            "type": "getPositions",
            "request_id": request_id
        }))
        
        try:
            response = await asyncio.wait_for(future, timeout=5.0)
            if response.get('type') == 'positions':
                return [Position.from_dict(p) for p in response.get('positions', [])]
            return []
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            return []
    
    async def ping(self) -> Dict[str, Any]:
        """
        Send ping to check connection
        """
        if not self._connected or not self.ws_connection:
            await self.connect_websocket()
        
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_requests[request_id] = future
        
        await self.ws_connection.send(json.dumps({
            "type": "ping",
            "request_id": request_id
        }))
        
        try:
            return await asyncio.wait_for(future, timeout=5.0)
        except asyncio.TimeoutError:
            self._pending_requests.pop(request_id, None)
            raise GatewayConnectionError("Ping timeout")
    
    # ==================== Callback Registration ====================
    
    def on_tick(self, symbol: str, callback: Callable[[Tick], Any]):
        """Register callback for tick updates"""
        if symbol not in self.tick_callbacks:
            self.tick_callbacks[symbol] = []
        self.tick_callbacks[symbol].append(callback)
    
    def on_quote(self, symbol: str, callback: Callable[[Quote], Any]):
        """Register callback for quote updates"""
        if symbol not in self.quote_callbacks:
            self.quote_callbacks[symbol] = []
        self.quote_callbacks[symbol].append(callback)
    
    def on_candle(self, symbol: str, timeframe: str, callback: Callable[[Candle], Any]):
        """Register callback for candle updates"""
        key = f"{symbol}:{timeframe}"
        if key not in self.candle_callbacks:
            self.candle_callbacks[key] = []
        self.candle_callbacks[key].append(callback)
    
    def on_position(self, callback: Callable[[Position], Any]):
        """Register callback for position updates"""
        self.position_callbacks.append(callback)
    
    def on_order_result(self, callback: Callable[[OrderResult], Any]):
        """Register callback for order results"""
        self.order_result_callbacks.append(callback)
    
    def on_account(self, callback: Callable[[AccountInfo], Any]):
        """Register callback for account updates"""
        self.account_callbacks.append(callback)
    
    def remove_tick_callback(self, symbol: str, callback: Callable):
        """Remove tick callback"""
        if symbol in self.tick_callbacks and callback in self.tick_callbacks[symbol]:
            self.tick_callbacks[symbol].remove(callback)
    
    def remove_all_callbacks(self):
        """Remove all callbacks"""
        self.tick_callbacks.clear()
        self.quote_callbacks.clear()
        self.candle_callbacks.clear()
        self.position_callbacks.clear()
        self.order_result_callbacks.clear()
        self.account_callbacks.clear()