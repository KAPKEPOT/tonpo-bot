# fx/services/trade_executor.py
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from sqlalchemy.orm import Session

from core.models import TradeSignal, CalculatedTrade
from services.signal_processor import SignalProcessor
#from core.parser import SignalParser
from services.mt5_manager import MT5ConnectionManager
from services.risk_service import RiskService
from services.subscription import SubscriptionService
from services.notification import NotificationService
from database.repositories import TradeRepository, UserRepository
from database.models import Trade

logger = logging.getLogger(__name__)


class TradeExecutionError(Exception):
    """Raised when trade execution fails"""
    pass


class TradeExecutor:
    def __init__(self, db_session: Session, bot=None, mt5_manager=None):
        self.db = db_session
        self.bot = bot
        
        # Initialize services
        self.signal_processor = SignalProcessor()
        #self.signal_processor = SignalParser()
        
        self.risk_service = RiskService()
        self.sub_service = SubscriptionService(db_session)
        self.notification = NotificationService(db_session, bot)
        self.mt5_manager = mt5_manager
        self.trade_repo = TradeRepository(db_session)
        self.user_repo = UserRepository(db_session)
        
        # Track in-progress trades
        self.pending_trades = {}
    
    async def execute_trade(self, user_id: int, signal_text: str, 
                           context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a trade from signal text
        """
        # Check if user already has a trade in progress
        if user_id in self.pending_trades:
            return {
                'success': False,
                'error': 'Trade already in progress',
                'status': 'pending_exists'
            }
        
        # Mark as pending
        self.pending_trades[user_id] = {
            'started_at': datetime.utcnow(),
            'signal': signal_text
        }
        
        try:
            # Step 1: Parse signal
            logger.info(f"Parsing signal for user {user_id}")
            signal = self.signal_processor.parse(signal_text)
            
            # Step 2: Check subscription limits
            can_trade, limit_info = self.sub_service.check_trade_limit(user_id)
            if not can_trade:
                await self.notification.notify_daily_limit(user_id, limit_info['limit'])
                return {
                    'success': False,
                    'error': 'Daily trade limit reached',
                    'limit_info': limit_info,
                    'status': 'limit_reached'
                }
            
            # Step 3: Get user and account info
            user = self.user_repo.get_by_telegram_id(user_id)
            if not user:
                raise TradeExecutionError("User not found")
            
            # Step 4: Get MT5 connection
            connection = await self.mt5_manager.get_connection(user_id)
            account_info = await connection.get_account_information()
            
            # Step 5: Get current price if market order
            if signal.is_market_order and signal.entry is None:
                price = await connection.get_symbol_price(signal.symbol)
                if signal.order_type.value in ['Buy', 'Buy Limit', 'Buy Stop']:
                    signal.entry = float(price['ask'])
                else:
                    signal.entry = float(price['bid'])
            
            # Step 6: Calculate risk
            user_settings = {
                'default_risk_factor': user.default_risk_factor,
                'max_position_size': user.max_position_size,
                'symbol_risk_overrides': user.settings.symbol_risk_overrides if user.settings else {}
            }
            
            calculated = self.risk_service.calculate_trade(
                signal=signal,
                balance=account_info['balance'],
                risk_factor=user.default_risk_factor,
                user_settings=user_settings
            )
            
            # Step 7: Check position size limit
            size_check, size_message = self.sub_service.check_position_size_limit(
                user_id, calculated.position_size
            )
            if not size_check:
                return {
                    'success': False,
                    'error': size_message,
                    'status': 'size_limit'
                }
            
            # Step 8: Check feature access (multiple TPs)
            if len(signal.take_profits) > 1:
                has_multiple_tps = self.sub_service.check_feature_access(user_id, 'multiple_tps')
                if not has_multiple_tps:
                    # Use only first TP
                    signal.take_profits = [signal.take_profits[0]]
                    calculated = self.risk_service.calculate_trade(
                        signal=signal,
                        balance=account_info['balance'],
                        risk_factor=user.default_risk_factor,
                        user_settings=user_settings
                    )
            
            # Step 9: Check for duplicates
            is_duplicate = self.signal_processor.is_duplicate(
                signal, 
                self._get_recent_signals(user_id)
            )
            if is_duplicate:
                return {
                    'success': False,
                    'error': 'Duplicate signal detected',
                    'status': 'duplicate'
                }
            
            # Step 10: Execute trade
            logger.info(f"Executing trade for user {user_id}: {signal}")
            
            trade_data = {
                'order_type': signal.order_type.value,
                'symbol': signal.symbol,
                'volume': calculated.position_size,
                'stop_loss': signal.stop_loss,
                'take_profit': signal.take_profits[0]  # First TP for execution
            }
            
            # For multiple TPs, we need to split
            if len(signal.take_profits) > 1:
                results = []
                size_per_tp = calculated.position_size / len(signal.take_profits)
                
                for tp in signal.take_profits:
                    trade_data['volume'] = size_per_tp
                    trade_data['take_profit'] = tp
                    
                    if signal.order_type.value in ['Buy', 'Sell']:
                        result = await self._execute_market_order(connection, trade_data)
                    else:
                        trade_data['price'] = signal.entry
                        result = await self._execute_pending_order(connection, trade_data)
                    
                    results.append(result)
            else:
                # Single TP execution
                if signal.order_type.value in ['Buy', 'Sell']:
                    result = await self._execute_market_order(connection, trade_data)
                else:
                    trade_data['price'] = signal.entry
                    result = await self._execute_pending_order(connection, trade_data)
                
                results = [result]
            
            # Step 11: Save trade to database
            trade_record = Trade(
                user_id=user.id,
                order_type=signal.order_type.value,
                symbol=signal.symbol,
                entry_price=signal.entry,
                stop_loss=signal.stop_loss,
                take_profits=signal.take_profits,
                position_size=calculated.position_size,
                risk_percentage=calculated.risk_percentage,
                risk_amount=calculated.potential_loss,
                potential_reward=calculated.total_potential_profit,
                mt_order_ids=[r.get('orderId') for r in results if r.get('orderId')],
                status='executed',
                signal_text=signal_text,
                signal_hash=self.signal_processor._calculate_hash(signal_text),
                executed_at=datetime.utcnow()
            )
            self.db.add(trade_record)
            
            # Step 12: Update user stats
            self.sub_service.increment_trade_count(user_id)
            user.total_volume += calculated.position_size
            
            self.db.commit()
            
            # Step 13: Send notifications
            await self.notification.notify_trade_executed(user_id, {
                'order_type': signal.order_type.value,
                'symbol': signal.symbol,
                'size': calculated.position_size,
                'risk': calculated.potential_loss,
                'reward': calculated.total_potential_profit,
                'rr_ratio': calculated.risk_reward_ratio
            })
            
            logger.info(f"Trade executed successfully for user {user_id}")
            
            return {
                'success': True,
                'trade_id': trade_record.uuid,
                'signal': {
                    'order_type': signal.order_type.value,
                    'symbol': signal.symbol,
                    'entry': signal.entry,
                    'stop_loss': signal.stop_loss,
                    'take_profits': signal.take_profits
                },
                'calculated': {
                    'position_size': calculated.position_size,
                    'risk_percentage': calculated.risk_percentage,
                    'potential_loss': calculated.potential_loss,
                    'potential_profit': calculated.total_potential_profit,
                    'risk_reward': calculated.risk_reward_ratio
                },
                'orders': results,
                'status': 'executed'
            }
            
        except Exception as e:
            logger.error(f"Trade execution failed for user {user_id}: {e}", exc_info=True)
            
            # Save failed trade
            try:
                user = self.user_repo.get_by_telegram_id(user_id)
                if user:
                	failed_trade = Trade(
                	    user_id=user.id,
                	    order_type='unknown',
                	    symbol='unknown',
                	    entry_price=0,
                	    stop_loss=0,
                	    take_profits=[0],
                	    position_size=0,
                	    risk_percentage=0,
                	    risk_amount=0,
                	    potential_reward=0,
                	    status='failed',
                	    error_message=str(e)[:500],
                	    signal_text=signal_text
                	)
                	self.db.add(failed_trade)
                	self.db.commit()
            except:
                pass
            
            # Send error notification
            await self.notification.notify_trade_failed(user_id, str(e), {
                'signal': signal_text[:100]
            })
            
            return {
                'success': False,
                'error': str(e),
                'status': 'failed'
            }
            
        finally:
            # Remove from pending
            self.pending_trades.pop(user_id, None)
    
    async def _execute_market_order(self, connection, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a market order"""
        if trade_data['order_type'] == 'Buy':
            return await connection.create_market_buy_order(
                trade_data['symbol'],
                trade_data['volume'],
                trade_data['stop_loss'],
                trade_data['take_profit']
            )
        else:
            return await connection.create_market_sell_order(
                trade_data['symbol'],
                trade_data['volume'],
                trade_data['stop_loss'],
                trade_data['take_profit']
            )
    
    async def _execute_pending_order(self, connection, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a pending order (limit/stop)"""
        order_map = {
            'Buy Limit': connection.create_limit_buy_order,
            'Sell Limit': connection.create_limit_sell_order,
            'Buy Stop': connection.create_stop_buy_order,
            'Sell Stop': connection.create_stop_sell_order
        }
        
        order_func = order_map.get(trade_data['order_type'])
        if not order_func:
            raise TradeExecutionError(f"Unsupported order type: {trade_data['order_type']}")
        
        return await order_func(
            trade_data['symbol'],
            trade_data['volume'],
            trade_data['price'],
            trade_data['stop_loss'],
            trade_data['take_profit']
        )
    
    async def calculate_only(self, user_id: int, signal_text: str) -> Dict[str, Any]:
        """Calculate trade metrics without executing"""
        try:
            # Parse signal
            signal = self.signal_processor.process(signal_text)
            
            # Get user and account info
            user = self.user_repo.get_by_telegram_id(user_id)
            if not user:
                raise TradeExecutionError("User not found")
            
            # Get MT5 connection for balance
            connection = await self.mt5_manager.get_connection(user_id)
            account_info = await connection.get_account_information()
            
            # Get current price if market order
            if signal.is_market_order and signal.entry is None:
                price = await connection.get_symbol_price(signal.symbol)
                if signal.order_type.value in ['Buy', 'Buy Limit', 'Buy Stop']:
                    signal.entry = float(price['ask'])
                else:
                    signal.entry = float(price['bid'])
            
            # Calculate risk
            user_settings = {
                'default_risk_factor': user.default_risk_factor,
                'max_position_size': user.max_position_size,
                'symbol_risk_overrides': user.settings.symbol_risk_overrides if user.settings else {}
            }
            
            calculated = self.risk_service.calculate_trade(
                signal=signal,
                balance=account_info['balance'],
                risk_factor=user.default_risk_factor,
                user_settings=user_settings
            )
            
            return {
                'success': True,
                'signal': {
                    'order_type': signal.order_type.value,
                    'symbol': signal.symbol,
                    'entry': signal.entry,
                    'stop_loss': signal.stop_loss,
                    'take_profits': signal.take_profits
                },
                'calculated': {
                    'position_size': calculated.position_size,
                    'stop_loss_pips': calculated.stop_loss_pips,
                    'take_profit_pips': calculated.take_profit_pips,
                    'risk_percentage': calculated.risk_percentage,
                    'potential_loss': calculated.potential_loss,
                    'potential_profits': calculated.potential_profits,
                    'total_profit': calculated.total_potential_profit,
                    'risk_reward': calculated.risk_reward_ratio
                },
                'account': {
                    'balance': account_info['balance'],
                    'currency': account_info.get('currency', 'USD')
                }
            }
            
        except Exception as e:
            logger.error(f"Calculation failed for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def close_trade(self, user_id: int, position_id: str) -> Dict[str, Any]:
        """Close an open position"""
        try:
            connection = await self.mt5_manager.get_connection(user_id)
            success = await self.mt5_manager.close_position(user_id, position_id)
            
            if success:
                # Update trade record
                trade = self.db.query(Trade).filter(
                    Trade.mt_order_ids.contains([position_id])
                ).first()
                
                if trade:
                    trade.status = 'closed'
                    trade.closed_at = datetime.utcnow()
                    self.db.commit()
                
                return {
                    'success': True,
                    'message': f'Position {position_id} closed successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to close position'
                }
                
        except Exception as e:
            logger.error(f"Failed to close position for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def modify_trade(self, user_id: int, position_id: str,
                          sl: Optional[float] = None, tp: Optional[float] = None) -> Dict[str, Any]:
        """Modify stop loss and take profit"""
        try:
            connection = await self.mt5_manager.get_connection(user_id)
            success = await self.mt5_manager.modify_position(user_id, position_id, sl, tp)
            
            if success:
                return {
                    'success': True,
                    'message': f'Position {position_id} modified successfully'
                }
            else:
                return {
                    'success': False,
                    'error': 'Failed to modify position'
                }
                
        except Exception as e:
            logger.error(f"Failed to modify position for user {user_id}: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_pending_trades(self, user_id: int) -> List[Dict[str, Any]]:
        """Get list of pending/executed trades"""
        trades = self.trade_repo.get_user_trades(user_id, limit=20)
        
        return [{
            'id': t.uuid,
            'order_type': t.order_type,
            'symbol': t.symbol,
            'entry': float(t.entry_price),
            'size': float(t.position_size),
            'status': t.status,
            'created_at': t.created_at.isoformat(),
            'profit_loss': float(t.profit_loss) if t.profit_loss else None
        } for t in trades]
    
    def _get_recent_signals(self, user_id: int, minutes: int = 5) -> List[TradeSignal]:
        """Get recent signals for duplicate detection"""
        from datetime import timedelta
        
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        recent_trades = self.db.query(Trade).filter(
            Trade.user_id == self.user_repo.get_by_telegram_id(user_id).id,
            Trade.created_at >= cutoff
        ).all()
        
        signals = []
        for trade in recent_trades:
            try:
                signal = TradeSignal(
                    order_type=trade.order_type,
                    symbol=trade.symbol,
                    entry=float(trade.entry_price),
                    stop_loss=float(trade.stop_loss),
                    take_profits=[float(tp) for tp in trade.take_profits]
                )
                signals.append(signal)
            except:
                continue
        
        return signals