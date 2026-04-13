# gateway_client/adapter.py
"""
Gateway adapter — replaces the hand-rolled gateway_client/client.py with
the official cipher_gateway SDK (pip install cipher-gateway).

External interface is unchanged:
  - GatewayConnectionAdapter  — used by trade_executor.py / trading.py
  - GatewayManager            — used by adapter.py / main.py
  - ExecutionProvider         — used by main.py

Internal implementation now delegates entirely to CipherGatewayClient.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List

from cipher_gateway import (
    CipherGatewayClient,
    GatewayConfig,
    AccountLoginFailedError,
    AccountTimeoutError,
    GatewayConnectionError,
    CipherGatewayError,
)

from config.settings import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GatewayConnectionAdapter
# ---------------------------------------------------------------------------
# Wraps one CipherGatewayClient (already authenticated for a single user).
# Methods match what trade_executor.py and trading.py call — untouched.

class GatewayConnectionAdapter:
    def __init__(self, client: CipherGatewayClient, user_id: str):
        self.client  = client
        self.user_id = user_id
        self._connected = True

    # ── Account ──────────────────────────────────────────────────────────────

    async def get_account_information(self) -> Dict[str, Any]:
        info = await self.client.get_account_info()
        return {
            'login':        info.login,
            'name':         info.name,
            'balance':      info.balance,
            'equity':       info.equity,
            'margin':       info.margin,
            'free_margin':  info.free_margin,
            'margin_level': info.margin_level,   # computed property on SDK model
            'currency':     info.currency,
            'server':       info.server,
            'leverage':     info.leverage,
            'profit':       info.profit,
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        positions = await self.client.get_positions()
        return [{
            'id':           p.ticket,
            'symbol':       p.symbol,
            'type':         p.side,
            'volume':       p.volume,
            'openPrice':    p.open_price,
            'currentPrice': p.current_price,
            'stopLoss':     p.sl,
            'takeProfit':   p.tp,
            'profit':       p.profit,
            'swap':         p.swap,
            'commission':   p.commission,
            'comment':      p.comment,
        } for p in positions]

    # ── Market orders ─────────────────────────────────────────────────────────

    async def create_market_buy_order(
        self, symbol: str, volume: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_market_buy(
            symbol, volume=volume, sl=sl, tp=tp, comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    async def create_market_sell_order(
        self, symbol: str, volume: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_market_sell(
            symbol, volume=volume, sl=sl, tp=tp, comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    # ── Limit orders ──────────────────────────────────────────────────────────

    async def create_limit_buy_order(
        self, symbol: str, volume: float, price: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_limit_buy(
            symbol, volume=volume, price=price, sl=sl, tp=tp,
            comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    async def create_limit_sell_order(
        self, symbol: str, volume: float, price: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_limit_sell(
            symbol, volume=volume, price=price, sl=sl, tp=tp,
            comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    # ── Stop orders ───────────────────────────────────────────────────────────

    async def create_stop_buy_order(
        self, symbol: str, volume: float, price: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_stop_buy(
            symbol, volume=volume, price=price, sl=sl, tp=tp,
            comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    async def create_stop_sell_order(
        self, symbol: str, volume: float, price: float,
        sl: Optional[float] = None, tp: Optional[float] = None,
        comment: Optional[str] = None, magic: Optional[int] = None
    ) -> Dict[str, Any]:
        result = await self.client.place_stop_sell(
            symbol, volume=volume, price=price, sl=sl, tp=tp,
            comment=comment, magic=magic
        )
        return {'orderId': str(result.ticket)} if result.success else {}

    # ── Position management ───────────────────────────────────────────────────

    async def close_position(self, position_id: str) -> bool:
        result = await self.client.close_position(ticket=int(position_id))
        return result.success

    async def modify_position(
        self, position_id: str,
        sl: Optional[float] = None, tp: Optional[float] = None
    ) -> bool:
        result = await self.client.modify_position(
            ticket=int(position_id), sl=sl, tp=tp
        )
        return result.success

    # ── Market data ───────────────────────────────────────────────────────────

    async def get_symbol_price(self, symbol: str) -> Dict[str, float]:
        """
        Get current bid/ask for a symbol.
        Uses the SDK's get_symbol_price which already falls back to the
        WebSocket price cache when the REST endpoint returns zeros.
        """
        try:
            price = await self.client.get_symbol_price(symbol)
            return {'bid': price.bid, 'ask': price.ask}
        except Exception as e:
            logger.warning(f"get_symbol_price({symbol}): {e}")
            raise RuntimeError(f"Unable to get price for {symbol}: {e}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def close(self):
        """Close this connection's underlying client."""
        self._connected = False
        try:
            await self.client.__aexit__(None, None, None)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# GatewayManager
# ---------------------------------------------------------------------------
# Manages one SDK client per user.  Public interface unchanged from before.

class GatewayManager:
    def __init__(self, gateway_config: Optional[GatewayConfig] = None):
        self.gateway_config: GatewayConfig = gateway_config or GatewayConfig()

        # Per-user live clients (created lazily in get_connection)
        self.user_clients:      Dict[int, CipherGatewayClient] = {}
        self.connections:       Dict[int, GatewayConnectionAdapter] = {}

        # Credentials loaded from DB on startup or stored after registration
        self.user_api_keys:     Dict[int, str] = {}
        self.user_gateway_ids:  Dict[int, str] = {}
        self.user_account_ids:  Dict[int, str] = {}

        self._ready       = asyncio.Event()
        self._ready_error: Optional[str] = None

        logger.info("GatewayManager initialised")

    async def start(self):
        """Health-check the gateway and mark the manager as ready."""
        logger.info("GatewayManager starting — checking gateway health...")
        try:
            async with CipherGatewayClient.admin(self.gateway_config) as client:
                healthy = await client.health_check()
            if healthy:
                self._ready.set()
                logger.info("GatewayManager ready ✅")
            else:
                self._ready_error = "Gateway health check returned unhealthy"
                logger.error(self._ready_error)
        except Exception as e:
            self._ready_error = f"Gateway unreachable: {e}"
            logger.error(self._ready_error)

    async def stop(self):
        """Close all open clients."""
        logger.info("GatewayManager stopping...")
        for telegram_id, client in list(self.user_clients.items()):
            try:
                await client.__aexit__(None, None, None)
            except Exception:
                pass
        self.user_clients.clear()
        self.connections.clear()
        logger.info("GatewayManager stopped")

    async def wait_until_ready(self, timeout: float = 30.0):
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
            return True, None
        except asyncio.TimeoutError:
            return False, self._ready_error or "Timeout"

    @property
    def is_ready(self) -> bool:
        return self._ready.is_set()

    # ── User registration ─────────────────────────────────────────────────────

    async def register_user(
        self,
        telegram_id: int,
        mt5_account:  str,
        mt5_password: str,
        mt5_server:   str,
    ) -> tuple:
        """
        Register a user with the gateway.
        Returns (success, message, credentials_dict).
        credentials_dict contains: gateway_user_id, gateway_api_key, gateway_account_id
        """
        try:
            # Subscription / connection-limit check
            try:
                from services.subscription import SubscriptionService
                from database.database import db_manager
                sub_service = SubscriptionService(db_manager.get_session())
                plan = sub_service.get_user_plan(telegram_id)
                current = sum(1 for uid in self.user_clients if uid == telegram_id)
                if plan and plan.max_connections and current >= plan.max_connections:
                    return (
                        False,
                        f"Connection limit reached ({plan.max_connections} for {plan.tier} plan)",
                        {},
                    )
            except Exception as e:
                logger.warning(f"Could not check connection limit: {e}")

            # Step 1: create a gateway user (no auth required)
            async with CipherGatewayClient.admin(self.gateway_config) as admin:
                user_creds = await admin.create_user()

            api_key          = user_creds.api_key
            gateway_user_id  = user_creds.gateway_user_id

            # Step 2 + 3 + 4: provision account and wait for MT5 to connect
            async with CipherGatewayClient.for_user(self.gateway_config, api_key) as client:
                account = await client.create_account(
                    mt5_login    = mt5_account,
                    mt5_password = mt5_password,
                    mt5_server   = mt5_server,
                )
                gateway_account_id = account.account_id

                try:
                    await client.wait_for_active(gateway_account_id, timeout=180)
                except AccountLoginFailedError as e:
                    # Clean up — wrong credentials, no point keeping the account
                    try:
                        await client.delete_account(gateway_account_id)
                    except Exception:
                        pass
                    return False, f"MT5 login failed — check credentials: {e}", {}
                except AccountTimeoutError as e:
                    try:
                        await client.delete_account(gateway_account_id)
                    except Exception:
                        pass
                    return False, f"MT5 did not connect in time: {e}", {}

            # Step 5: store credentials in memory
            self.user_gateway_ids[telegram_id] = gateway_user_id
            self.user_api_keys[telegram_id]    = api_key
            self.user_account_ids[telegram_id] = gateway_account_id

            logger.info(
                f"User {telegram_id} registered "
                f"(gw_id={gateway_user_id}, account={gateway_account_id})"
            )
            return True, "Connected successfully", {
                'gateway_user_id':   gateway_user_id,
                'gateway_api_key':   api_key,
                'gateway_account_id': gateway_account_id,
            }

        except CipherGatewayError as e:
            logger.error(f"Gateway registration failed for {telegram_id}: {e}")
            self.user_clients.pop(telegram_id, None)
            self.user_api_keys.pop(telegram_id, None)
            self.user_gateway_ids.pop(telegram_id, None)
            return False, str(e), {}
        except Exception as e:
            logger.error(f"Unexpected error registering {telegram_id}: {e}")
            self.user_clients.pop(telegram_id, None)
            self.user_api_keys.pop(telegram_id, None)
            self.user_gateway_ids.pop(telegram_id, None)
            return False, str(e), {}

    # ── Connection access ─────────────────────────────────────────────────────

    async def get_connection(self, telegram_id: int) -> GatewayConnectionAdapter:
        """
        Return a GatewayConnectionAdapter for the given user.
        The SDK client is created lazily — once per user, reused thereafter.
        """
        if telegram_id in self.connections:
            return self.connections[telegram_id]

        if telegram_id not in self.user_api_keys:
            raise ValueError(f"User {telegram_id} not registered with gateway")

        # Create and start SDK client if not already alive
        if telegram_id not in self.user_clients:
            api_key = self.user_api_keys[telegram_id]
            client  = CipherGatewayClient.for_user(self.gateway_config, api_key)
            await client.__aenter__()
            self.user_clients[telegram_id] = client

        connection = GatewayConnectionAdapter(
            self.user_clients[telegram_id],
            self.user_account_ids.get(telegram_id, ""),
        )
        self.connections[telegram_id] = connection
        logger.info(f"Created gateway connection for user {telegram_id}")
        return connection

    async def close_connection(self, telegram_id: int):
        """Close a user's connection and release the SDK client."""
        if telegram_id in self.connections:
            await self.connections.pop(telegram_id).close()

        if telegram_id in self.user_clients:
            try:
                await self.user_clients.pop(telegram_id).__aexit__(None, None, None)
            except Exception:
                pass

        logger.info(f"Closed gateway connection for user {telegram_id}")

    def get_connection_status(self, telegram_id: int) -> bool:
        return telegram_id in self.connections

    def load_user_credentials(
        self,
        telegram_id:        int,
        api_key:            str,
        gateway_account_id: str,
    ):
        """
        Restore credentials from the database on bot startup.
        The SDK client is created lazily on first get_connection() call.
        """
        self.user_api_keys[telegram_id]    = api_key
        self.user_account_ids[telegram_id] = gateway_account_id


# ---------------------------------------------------------------------------
# ExecutionProvider
# ---------------------------------------------------------------------------
# Thin wrapper used by main.py — unchanged public interface.

class ExecutionProvider:
    def __init__(self, use_gateway: bool = True):
        self.use_gateway              = use_gateway
        self.gateway_manager: Optional[GatewayManager] = None

    async def initialize(self, gateway_config: Optional[GatewayConfig] = None):
        self.gateway_manager = GatewayManager(gateway_config)
        await self.gateway_manager.start()

    async def shutdown(self):
        if self.gateway_manager:
            await self.gateway_manager.stop()

    async def health_check(self) -> bool:
        if not self.gateway_manager:
            return False
        try:
            async with CipherGatewayClient.admin(
                self.gateway_manager.gateway_config
            ) as client:
                return await client.health_check()
        except Exception:
            return False

    async def get_connection(self, user_id: int) -> GatewayConnectionAdapter:
        if not self.gateway_manager:
            raise RuntimeError("Gateway not initialised")
        return await self.gateway_manager.get_connection(user_id)

    async def register_user(
        self,
        telegram_id:  int,
        mt5_account:  str,
        mt5_password: str,
        mt5_server:   str,
    ) -> tuple:
        if not self.gateway_manager:
            return False, "Gateway not initialised", {}
        try:
            return await self.gateway_manager.register_user(
                telegram_id, mt5_account, mt5_password, mt5_server
            )
        except Exception as e:
            logger.error(f"Registration failed for {telegram_id}: {e}")
            return False, str(e), {}
