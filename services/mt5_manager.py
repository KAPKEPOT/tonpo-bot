# fx/services/mt5_manager.py
import asyncio
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta
import logging
from contextlib import asynccontextmanager
import time

from metaapi_cloud_sdk import MetaApi
from sqlalchemy.orm import Session

from database.repositories import UserRepository, ConnectionLogRepository
from services.auth import EncryptionService
from config.settings import settings

logger = logging.getLogger(__name__)


class ConnectionPool:
    """
    Manages a pool of MetaTrader connections
    Implements connection reuse and automatic cleanup
    """
    
    def __init__(self, max_connections: int = 100, idle_timeout: int = 300):
        self.max_connections = max_connections
        self.idle_timeout = idle_timeout  # seconds
        self.connections: Dict[int, Dict[str, Any]] = {}
        self.locks: Dict[int, asyncio.Lock] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the connection pool cleanup task"""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Connection pool started")
    
    async def stop(self):
        """Stop the connection pool and close all connections"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        
        # Close all connections
        for user_id in list(self.connections.keys()):
            await self.close_connection(user_id)
        
        logger.info("Connection pool stopped")
    
    async def get_connection(self, user_id: int, api: MetaApi, account_id: str):
        """
        Get or create a connection for a user
        """
        if user_id not in self.locks:
            self.locks[user_id] = asyncio.Lock()
        
        async with self.locks[user_id]:
            # Check if we have a valid connection
            if user_id in self.connections:
                conn_info = self.connections[user_id]
                
                # Check if connection is still valid
                if datetime.utcnow() - conn_info['created_at'] < timedelta(seconds=self.idle_timeout):
                    conn_info['last_used'] = datetime.utcnow()
                    return conn_info['connection']
                else:
                    # Close old connection
                    await self.close_connection(user_id)
            
            # Create new connection
            try:
                account = await api.metatrader_account_api.get_account(account_id)
                
                # Deploy if needed
                if account.state not in ['DEPLOYING', 'DEPLOYED']:
                    logger.info(f"Deploying account for user {user_id}")
                    await account.deploy()
                
                logger.info(f"Waiting for connection for user {user_id}")
                await account.wait_connected()
                
                # Create RPC connection
                connection = account.get_rpc_connection()
                await connection.connect()
                
                logger.info(f"Waiting for synchronization for user {user_id}")
                await connection.wait_synchronized()
                
                # Store connection
                self.connections[user_id] = {
                    'connection': connection,
                    'created_at': datetime.utcnow(),
                    'last_used': datetime.utcnow(),
                    'account_id': account_id
                }
                
                logger.info(f"Created new connection for user {user_id}")
                return connection
                
            except Exception as e:
                logger.error(f"Failed to create connection for user {user_id}: {e}")
                raise
    
    async def close_connection(self, user_id: int):
        """Close a specific user's connection"""
        if user_id in self.connections:
            try:
                await self.connections[user_id]['connection'].close()
                logger.info(f"Closed connection for user {user_id}")
            except Exception as e:
                logger.error(f"Error closing connection for user {user_id}: {e}")
            finally:
                del self.connections[user_id]
    
    async def _cleanup_loop(self):
        """Periodically clean up idle connections"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                now = datetime.utcnow()
                for user_id in list(self.connections.keys()):
                    conn_info = self.connections.get(user_id)
                    if conn_info:
                        idle_time = (now - conn_info['last_used']).total_seconds()
                        if idle_time > self.idle_timeout:
                            logger.info(f"Closing idle connection for user {user_id} "
                                       f"(idle for {idle_time:.0f}s)")
                            await self.close_connection(user_id)
                            
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")


class MT5ConnectionManager:
    """
    Manages MetaTrader connections and trade execution
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.user_repo = UserRepository(db_session)
        self.connection_log_repo = ConnectionLogRepository(db_session)
        self.encryption = EncryptionService()
        
        # Initialize MetaAPI
        self.api = MetaApi(settings.METAAPI_TOKEN)
        
        # Initialize connection pool
        self.pool = ConnectionPool(
            max_connections=settings.MAX_CONNECTIONS,
            idle_timeout=settings.CONNECTION_IDLE_TIMEOUT
        )
        
        # Track connection status
        self.connection_status: Dict[int, bool] = {}
    
    async def start(self):
        """Start the connection manager"""
        await self.pool.start()
        logger.info("MT5 Connection Manager started")
    
    async def stop(self):
        """Stop the connection manager"""
        await self.pool.stop()
        logger.info("MT5 Connection Manager stopped")
    
    async def connect_user(self, user_id: int, mt5_account: str, mt5_password: str, 
                          mt5_server: str) -> Tuple[bool, str]:
        """
        Connect a user's MT5 account
        This is used during registration to verify credentials
        """
        start_time = time.time()
        
        try:
            # Decrypt password
            decrypted_password = self.encryption.decrypt(mt5_password)
            
            # Get or create MetaAPI account
            account = await self._get_or_create_account(
                user_id, mt5_account, decrypted_password, mt5_server
            )
            
            # Test connection
            connection = await self.pool.get_connection(user_id, self.api, account.id)
            
            # Get account info to verify
            account_info = await connection.get_account_information()
            
            # Update user's connection status
            self.user_repo.update_user(
                user_id,
                mt_connected=True,
                last_connected=datetime.utcnow(),
                connection_error=None,
                connection_attempts=0
            )
            
            # Log successful connection
            latency = int((time.time() - start_time) * 1000)
            self.connection_log_repo.log_connection(
                user_id=user_id,
                status='success',
                latency_ms=latency,
                server=mt5_server,
                account_type='demo' if 'demo' in mt5_server.lower() else 'real'
            )
            
            self.connection_status[user_id] = True
            logger.info(f"Successfully connected user {user_id} to MT5")
            
            return True, "Connected successfully"
            
        except Exception as e:
            logger.error(f"Failed to connect user {user_id}: {e}")
            
            # Update user's connection status (only if user row exists)
            existing_user = self.user_repo.get_by_telegram_id(user_id)
            self.user_repo.update_user(
                user_id,
                mt_connected=False,
                connection_error=str(e)[:200],
                connection_attempts=(existing_user.connection_attempts + 1) if existing_user else 1
            )
            
            # Log failed connection
            latency = int((time.time() - start_time) * 1000)
            self.connection_log_repo.log_connection(
                user_id=user_id,
                status='failed',
                error=str(e),
                latency_ms=latency,
                server=mt5_server
            )
            
            self.connection_status[user_id] = False
            return False, str(e)
    
    async def _get_or_create_account(self, user_id: int, account_id: str, 
                                     password: str, server: str):
        """
        Get existing MetaAPI account or create a new one
        """
        try:
            # Try to get existing account
            account = await self.api.metatrader_account_api.get_account(account_id)
            logger.info(f"Found existing account for user {user_id}")
            return account
        except Exception:
            if "404" in str(e) or "not found" in str(e).lower():
            	
            	# Account doesn't exist, create new one
            	logger.info(f"Creating new account for user {user_id}")
            	
            	try:
            		account = await self.api.metatrader_account_api.create_account({
            		    'name': f"User_{user_id}",
            		    'type': 'cloud',
            		    'login': account_id,
            		    'password': password,
            		    'server': server,
            		    'platform': 'mt5',
            		    'magic': 123456,
            		    'application': 'FX Signal Copier'
            		})
            		return account
            	except Exception as create_error:
            		if "top up your account" in str(create_error).lower():
            			logger.error(f"MetaAPI account needs funding: {create_error}")
            			raise Exception("MetaAPI service requires payment. Please contact support.")
            		else:
            			raise
            else:
            	# Re-raise other errors
            	raise
            	
    async def get_connection(self, user_id: int):
        """
        Get a connection for a user from the pool
        """
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        
        # Decrypt password
        password = self.encryption.decrypt(user.mt5_password)
        
        # Get or create account
        account = await self._get_or_create_account(
            user_id, user.mt5_account_id, password, user.mt5_server
        )
        
        # Get connection from pool
        connection = await self.pool.get_connection(user_id, self.api, account.id)
        
        # Update last used
        user.last_connected = datetime.utcnow()
        self.db.commit()
        
        return connection
    
    async def execute_trade(self, user_id: int, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a trade for a user
        """
        connection = await self.get_connection(user_id)
        
        try:
            # Get account info for validation
            account_info = await connection.get_account_information()
            
            # Validate trade against account
            if account_info['balance'] < trade_data.get('required_margin', 0):
                raise ValueError("Insufficient balance")
            
            # Execute based on order type
            order_type = trade_data['order_type']
            symbol = trade_data['symbol']
            volume = trade_data['volume']
            sl = trade_data.get('stop_loss')
            tp = trade_data.get('take_profit')
            
            results = []
            
            if order_type == 'Buy':
                result = await connection.create_market_buy_order(symbol, volume, sl, tp)
                results.append(result)
            elif order_type == 'Sell':
                result = await connection.create_market_sell_order(symbol, volume, sl, tp)
                results.append(result)
            elif order_type == 'Buy Limit':
                result = await connection.create_limit_buy_order(
                    symbol, volume, trade_data['price'], sl, tp
                )
                results.append(result)
            elif order_type == 'Sell Limit':
                result = await connection.create_limit_sell_order(
                    symbol, volume, trade_data['price'], sl, tp
                )
                results.append(result)
            elif order_type == 'Buy Stop':
                result = await connection.create_stop_buy_order(
                    symbol, volume, trade_data['price'], sl, tp
                )
                results.append(result)
            elif order_type == 'Sell Stop':
                result = await connection.create_stop_sell_order(
                    symbol, volume, trade_data['price'], sl, tp
                )
                results.append(result)
            
            logger.info(f"Trade executed for user {user_id}: {results}")
            
            return {
                'success': True,
                'orders': results,
                'message': 'Trade executed successfully'
            }
            
        except Exception as e:
            logger.error(f"Trade execution failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Trade execution failed'
            }
    
    async def get_account_info(self, user_id: int) -> Dict[str, Any]:
        """
        Get account information for a user
        """
        connection = await self.get_connection(user_id)
        return await connection.get_account_information()
    
    async def get_positions(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Get open positions for a user
        """
        connection = await self.get_connection(user_id)
        return await connection.get_positions()
    
    async def get_symbol_price(self, user_id: int, symbol: str) -> Dict[str, float]:
        """
        Get current price for a symbol
        """
        connection = await self.get_connection(user_id)
        return await connection.get_symbol_price(symbol)
    
    async def close_position(self, user_id: int, position_id: str) -> bool:
        """
        Close a specific position
        """
        connection = await self.get_connection(user_id)
        try:
            await connection.close_position(position_id)
            return True
        except Exception as e:
            logger.error(f"Failed to close position {position_id} for user {user_id}: {e}")
            return False
    
    async def modify_position(self, user_id: int, position_id: str, 
                             sl: Optional[float] = None, tp: Optional[float] = None) -> bool:
        """
        Modify a position's stop loss and take profit
        """
        connection = await self.get_connection(user_id)
        try:
            await connection.modify_position(position_id, sl, tp)
            return True
        except Exception as e:
            logger.error(f"Failed to modify position {position_id} for user {user_id}: {e}")
            return False
    
    @asynccontextmanager
    async def temporary_connection(self, user_id: int):
        """
        Context manager for temporary connection usage
        """
        connection = None
        try:
            connection = await self.get_connection(user_id)
            yield connection
        finally:
            # Connection will be kept in pool, not closed
            pass
    
    def get_connection_status(self, user_id: int) -> bool:
        """Get current connection status for a user"""
        return self.connection_status.get(user_id, False)