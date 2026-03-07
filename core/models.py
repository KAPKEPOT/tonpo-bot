# fx/core/models.py
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from decimal import Decimal
import json

from config.constants import OrderType


@dataclass
class TradeSignal:
    """
    Represents a parsed trading signal from user input
    """
    order_type: OrderType
    symbol: str
    entry: Optional[float] = None  # None for market orders (NOW)
    stop_loss: float = 0.0
    take_profits: List[float] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Validate after initialization"""
        if self.take_profits and len(self.take_profits) > 2:
            self.take_profits = self.take_profits[:2]  # Max 2 TPs
    
    @property
    def has_multiple_tps(self) -> bool:
        """Check if signal has multiple take profits"""
        return len(self.take_profits) > 1
    
    @property
    def is_market_order(self) -> bool:
        """Check if this is a market order (entry = None)"""
        return self.order_type in [OrderType.BUY, OrderType.SELL] and self.entry is None
    
    @property
    def is_limit_order(self) -> bool:
        """Check if this is a limit order"""
        return self.order_type in [OrderType.BUY_LIMIT, OrderType.SELL_LIMIT]
    
    @property
    def is_stop_order(self) -> bool:
        """Check if this is a stop order"""
        return self.order_type in [OrderType.BUY_STOP, OrderType.SELL_STOP]
    
    @property
    def is_pending_order(self) -> bool:
        """Check if this is a pending order (limit/stop)"""
        return self.is_limit_order or self.is_stop_order
    
    @property
    def is_buy(self) -> bool:
        """Check if this is a buy order"""
        return 'Buy' in self.order_type.value
    
    @property
    def is_sell(self) -> bool:
        """Check if this is a sell order"""
        return 'Sell' in self.order_type.value
    
    @property
    def direction(self) -> str:
        """Get trade direction (LONG/SHORT)"""
        return "LONG" if self.is_buy else "SHORT"
    
    def validate(self) -> List[str]:
        """
        Validate signal data
        Returns list of validation errors (empty if valid)
        """
        errors = []
        
        # Check required fields
        if not self.symbol:
            errors.append("Symbol is required")
        
        if not self.stop_loss or self.stop_loss <= 0:
            errors.append("Valid stop loss is required")
        
        if not self.take_profits:
            errors.append("At least one take profit is required")
        
        # Check entry for pending orders
        if self.is_pending_order and (self.entry is None or self.entry <= 0):
            errors.append("Entry price required for limit/stop orders")
        
        # Validate price relationships
        if self.entry and self.stop_loss:
            if self.is_buy and self.stop_loss >= self.entry:
                errors.append("Stop loss must be below entry for BUY orders")
            elif self.is_sell and self.stop_loss <= self.entry:
                errors.append("Stop loss must be above entry for SELL orders")
        
        # Validate take profits
        for i, tp in enumerate(self.take_profits):
            if self.entry:
                if self.is_buy and tp <= self.entry:
                    errors.append(f"TP{i+1} must be above entry for BUY orders")
                elif self.is_sell and tp >= self.entry:
                    errors.append(f"TP{i+1} must be below entry for SELL orders")
        
        return errors
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'order_type': self.order_type.value,
            'symbol': self.symbol,
            'entry': self.entry,
            'stop_loss': self.stop_loss,
            'take_profits': self.take_profits,
            'metadata': self.metadata,
            'is_market_order': self.is_market_order,
            'direction': self.direction
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradeSignal':
        """Create TradeSignal from dictionary"""
        return cls(
            order_type=OrderType(data['order_type']),
            symbol=data['symbol'],
            entry=data.get('entry'),
            stop_loss=data['stop_loss'],
            take_profits=data.get('take_profits', []),
            metadata=data.get('metadata', {})
        )
    
    def __str__(self) -> str:
        """String representation"""
        tps = ', '.join([f"{tp:.5f}" for tp in self.take_profits])
        entry_str = f"{self.entry:.5f}" if self.entry else "MARKET"
        return f"{self.order_type.value} {self.symbol} @ {entry_str} SL:{self.stop_loss:.5f} TP:[{tps}]"


@dataclass
class CalculatedTrade:
    """
    Trade with calculated risk metrics after position sizing
    """
    signal: TradeSignal
    balance: float
    position_size: float
    stop_loss_pips: int
    take_profit_pips: List[int]
    potential_loss: float
    potential_profits: List[float]
    risk_percentage: float
    risk_reward_ratio: float = 0.0
    account_currency: str = "USD"
    
    def __post_init__(self):
        """Calculate derived values"""
        if self.potential_loss > 0:
            self.risk_reward_ratio = self.total_potential_profit / self.potential_loss
    
    @property
    def total_potential_profit(self) -> float:
        """Get total potential profit from all TPs"""
        return sum(self.potential_profits)
    
    @property
    def risk_amount(self) -> float:
        """Alias for potential_loss"""
        return self.potential_loss
    
    @property
    def reward_amount(self) -> float:
        """Alias for total_potential_profit"""
        return self.total_potential_profit
    
    @property
    def is_valid(self) -> bool:
        """Check if trade calculations are valid"""
        return (self.position_size > 0 and 
                self.stop_loss_pips > 0 and 
                self.risk_percentage > 0 and
                self.potential_loss > 0)
    
    @property
    def tp_count(self) -> int:
        """Number of take profit levels"""
        return len(self.take_profit_pips)
    
    def get_tp_profit(self, index: int) -> float:
        """Get profit for specific TP index"""
        if 0 <= index < len(self.potential_profits):
            return self.potential_profits[index]
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'signal': self.signal.to_dict(),
            'balance': self.balance,
            'position_size': self.position_size,
            'stop_loss_pips': self.stop_loss_pips,
            'take_profit_pips': self.take_profit_pips,
            'potential_loss': self.potential_loss,
            'potential_profits': self.potential_profits,
            'total_profit': self.total_potential_profit,
            'risk_percentage': self.risk_percentage,
            'risk_reward_ratio': self.risk_reward_ratio,
            'account_currency': self.account_currency,
            'is_valid': self.is_valid
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CalculatedTrade':
        """Create CalculatedTrade from dictionary"""
        return cls(
            signal=TradeSignal.from_dict(data['signal']),
            balance=data['balance'],
            position_size=data['position_size'],
            stop_loss_pips=data['stop_loss_pips'],
            take_profit_pips=data['take_profit_pips'],
            potential_loss=data['potential_loss'],
            potential_profits=data['potential_profits'],
            risk_percentage=data['risk_percentage'],
            risk_reward_ratio=data.get('risk_reward_ratio', 0.0),
            account_currency=data.get('account_currency', 'USD')
        )
    
    def __str__(self) -> str:
        """String representation"""
        return (f"Size: {self.position_size:.2f} | "
                f"Risk: {self.risk_percentage:.1f}% (${self.potential_loss:.2f}) | "
                f"Reward: ${self.total_potential_profit:.2f} | "
                f"R:R: 1:{self.risk_reward_ratio:.2f}")


@dataclass
class Position:
    """
    Represents an open trading position from MT5
    """
    id: str
    symbol: str
    type: str  # 'buy' or 'sell'
    volume: float
    open_price: float
    current_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    comment: Optional[str] = None
    magic: int = 0
    open_time: Optional[datetime] = None
    expiration: Optional[datetime] = None
    
    @property
    def is_buy(self) -> bool:
        """Check if position is long"""
        return self.type.lower() == 'buy'
    
    @property
    def is_sell(self) -> bool:
        """Check if position is short"""
        return self.type.lower() == 'sell'
    
    @property
    def direction(self) -> str:
        """Get position direction"""
        return "LONG" if self.is_buy else "SHORT"
    
    @property
    def pips(self) -> float:
        """Calculate profit/loss in pips"""
        if self.is_buy:
            return (self.current_price - self.open_price) / self._get_pip_value()
        else:
            return (self.open_price - self.current_price) / self._get_pip_value()
    
    @property
    def total_profit(self) -> float:
        """Total profit including swap and commission"""
        return self.profit + self.swap - self.commission
    
    @property
    def is_profitable(self) -> bool:
        """Check if position is in profit"""
        return self.total_profit > 0
    
    @property
    def is_in_loss(self) -> bool:
        """Check if position is in loss"""
        return self.total_profit < 0
    
    @property
    def distance_to_sl(self) -> Optional[float]:
        """Distance to stop loss in pips"""
        if not self.stop_loss:
            return None
        if self.is_buy:
            return (self.current_price - self.stop_loss) / self._get_pip_value()
        else:
            return (self.stop_loss - self.current_price) / self._get_pip_value()
    
    @property
    def distance_to_tp(self) -> Optional[float]:
        """Distance to take profit in pips"""
        if not self.take_profit:
            return None
        if self.is_buy:
            return (self.take_profit - self.current_price) / self._get_pip_value()
        else:
            return (self.current_price - self.take_profit) / self._get_pip_value()
    
    def _get_pip_value(self) -> float:
        """Get pip value based on symbol"""
        if 'JPY' in self.symbol:
            return 0.01
        elif self.symbol in ['XAUUSD', 'XAGUSD']:
            return 0.1 if self.symbol == 'XAUUSD' else 0.001
        else:
            return 0.0001
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'symbol': self.symbol,
            'type': self.type,
            'volume': self.volume,
            'open_price': self.open_price,
            'current_price': self.current_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'profit': self.profit,
            'swap': self.swap,
            'commission': self.commission,
            'total_profit': self.total_profit,
            'comment': self.comment,
            'magic': self.magic,
            'open_time': self.open_time.isoformat() if self.open_time else None,
            'expiration': self.expiration.isoformat() if self.expiration else None,
            'pips': self.pips,
            'direction': self.direction
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create Position from dictionary"""
        return cls(
            id=data['id'],
            symbol=data['symbol'],
            type=data['type'],
            volume=data['volume'],
            open_price=data['open_price'],
            current_price=data['current_price'],
            stop_loss=data.get('stop_loss'),
            take_profit=data.get('take_profit'),
            profit=data.get('profit', 0.0),
            swap=data.get('swap', 0.0),
            commission=data.get('commission', 0.0),
            comment=data.get('comment'),
            magic=data.get('magic', 0),
            open_time=datetime.fromisoformat(data['open_time']) if data.get('open_time') else None,
            expiration=datetime.fromisoformat(data['expiration']) if data.get('expiration') else None
        )
    
    def __str__(self) -> str:
        """String representation"""
        status = "✅" if self.is_profitable else "❌" if self.is_in_loss else "⏳"
        return (f"{status} {self.symbol} {self.direction} "
                f"Vol:{self.volume:.2f} "
                f"Profit:${self.total_profit:.2f}")


@dataclass
class AccountInfo:
    """
    Represents MT5 account information
    """
    login: int
    balance: float
    equity: float
    margin: float
    free_margin: float
    margin_level: float
    currency: str
    server: str
    broker: Optional[str] = None
    name: Optional[str] = None
    leverage: int = 0
    profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    floating_profit: float = 0.0
    
    @property
    def is_margin_call(self) -> bool:
        """Check if account is in margin call"""
        return self.margin_level < 100
    
    @property
    def is_stop_out(self) -> bool:
        """Check if account is in stop out"""
        return self.margin_level < 50
    
    @property
    def margin_used_percent(self) -> float:
        """Calculate margin usage percentage"""
        if self.balance == 0:
            return 0.0
        return (self.margin / self.balance) * 100
    
    @property
    def available_to_trade(self) -> float:
        """Calculate available funds for new trades"""
        return self.free_margin
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'login': self.login,
            'balance': self.balance,
            'equity': self.equity,
            'margin': self.margin,
            'free_margin': self.free_margin,
            'margin_level': self.margin_level,
            'currency': self.currency,
            'server': self.server,
            'broker': self.broker,
            'name': self.name,
            'leverage': self.leverage,
            'profit': self.profit,
            'swap': self.swap,
            'commission': self.commission,
            'floating_profit': self.floating_profit,
            'margin_used_percent': self.margin_used_percent,
            'is_margin_call': self.is_margin_call
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AccountInfo':
        """Create AccountInfo from dictionary"""
        return cls(
            login=data['login'],
            balance=data['balance'],
            equity=data['equity'],
            margin=data['margin'],
            free_margin=data['free_margin'],
            margin_level=data['margin_level'],
            currency=data['currency'],
            server=data['server'],
            broker=data.get('broker'),
            name=data.get('name'),
            leverage=data.get('leverage', 0),
            profit=data.get('profit', 0.0),
            swap=data.get('swap', 0.0),
            commission=data.get('commission', 0.0),
            floating_profit=data.get('floating_profit', 0.0)
        )
    
    def __str__(self) -> str:
        """String representation"""
        return (f"Account {self.login} @ {self.server}\n"
                f"Balance: {self.currency} {self.balance:,.2f}\n"
                f"Equity: {self.currency} {self.equity:,.2f}\n"
                f"Free Margin: {self.currency} {self.free_margin:,.2f}\n"
                f"Margin Level: {self.margin_level:.2f}%")


@dataclass
class OrderResult:
    """
    Result of an order execution
    """
    order_id: str
    symbol: str
    type: str
    volume: float
    price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    comment: Optional[str] = None
    magic: int = 0
    state: str = 'filled'  # filled, pending, cancelled, rejected
    error: Optional[str] = None
    execution_time: Optional[datetime] = None
    
    @property
    def is_success(self) -> bool:
        """Check if order was successful"""
        return self.state == 'filled' and not self.error
    
    @property
    def is_pending(self) -> bool:
        """Check if order is pending"""
        return self.state == 'pending'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'order_id': self.order_id,
            'symbol': self.symbol,
            'type': self.type,
            'volume': self.volume,
            'price': self.price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'comment': self.comment,
            'magic': self.magic,
            'state': self.state,
            'error': self.error,
            'execution_time': self.execution_time.isoformat() if self.execution_time else None
        }
    
    def __str__(self) -> str:
        """String representation"""
        if self.is_success:
            return f"✅ {self.type} {self.symbol} {self.volume} @ {self.price}"
        else:
            return f"❌ {self.type} {self.symbol} failed: {self.error}"


@dataclass
class SignalHistory:
    """
    Represents a historical signal for tracking
    """
    id: str
    user_id: int
    signal: TradeSignal
    status: str  # received, processed, executed, failed
    created_at: datetime
    executed_at: Optional[datetime] = None
    result: Optional[OrderResult] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def processing_time(self) -> Optional[float]:
        """Calculate processing time in seconds"""
        if self.executed_at:
            return (self.executed_at - self.created_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'signal': self.signal.to_dict(),
            'status': self.status,
            'created_at': self.created_at.isoformat(),
            'executed_at': self.executed_at.isoformat() if self.executed_at else None,
            'result': self.result.to_dict() if self.result else None,
            'error': self.error,
            'metadata': self.metadata,
            'processing_time': self.processing_time
        }


@dataclass
class UserPreferences:
    """
    User trading preferences
    """
    user_id: int
    default_risk_factor: float = 0.01
    max_position_size: float = 10.0
    allowed_symbols: List[str] = field(default_factory=list)
    blocked_symbols: List[str] = field(default_factory=list)
    notify_on_trade: bool = True
    notify_on_error: bool = True
    notify_daily_report: bool = False
    auto_trading_enabled: bool = False
    language: str = 'en'
    
    def is_symbol_allowed(self, symbol: str) -> bool:
        """Check if symbol is allowed for trading"""
        if self.blocked_symbols and symbol in self.blocked_symbols:
            return False
        if self.allowed_symbols and symbol not in self.allowed_symbols:
            return False
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'user_id': self.user_id,
            'default_risk_factor': self.default_risk_factor,
            'max_position_size': self.max_position_size,
            'allowed_symbols': self.allowed_symbols,
            'blocked_symbols': self.blocked_symbols,
            'notify_on_trade': self.notify_on_trade,
            'notify_on_error': self.notify_on_error,
            'notify_daily_report': self.notify_daily_report,
            'auto_trading_enabled': self.auto_trading_enabled,
            'language': self.language
        }


@dataclass
class PriceQuote:
    """
    Real-time price quote for a symbol
    """
    symbol: str
    bid: float
    ask: float
    spread: float
    timestamp: datetime
    volume: Optional[float] = None
    
    @property
    def mid(self) -> float:
        """Calculate mid price"""
        return (self.bid + self.ask) / 2
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'bid': self.bid,
            'ask': self.ask,
            'spread': self.spread,
            'mid': self.mid,
            'timestamp': self.timestamp.isoformat(),
            'volume': self.volume
        }


@dataclass
class MarketCondition:
    """
    Market condition analysis
    """
    symbol: str
    volatility: float  # ATR or similar
    trend: str  # bullish, bearish, ranging
    support_levels: List[float] = field(default_factory=list)
    resistance_levels: List[float] = field(default_factory=list)
    spread: float = 0.0
    session: str = ""  # asian, london, ny, etc.
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'volatility': self.volatility,
            'trend': self.trend,
            'support_levels': self.support_levels,
            'resistance_levels': self.resistance_levels,
            'spread': self.spread,
            'session': self.session
        }


class SignalBatch:
    """
    Collection of signals for batch processing
    """
    def __init__(self, signals: List[TradeSignal] = None):
        self.signals = signals or []
        self.created_at = datetime.utcnow()
    
    def add_signal(self, signal: TradeSignal):
        """Add signal to batch"""
        self.signals.append(signal)
    
    def remove_signal(self, index: int):
        """Remove signal from batch"""
        if 0 <= index < len(self.signals):
            self.signals.pop(index)
    
    @property
    def count(self) -> int:
        """Get number of signals in batch"""
        return len(self.signals)
    
    @property
    def symbols(self) -> List[str]:
        """Get unique symbols in batch"""
        return list(set(s.symbol for s in self.signals))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'signals': [s.to_dict() for s in self.signals],
            'count': self.count,
            'symbols': self.symbols,
            'created_at': self.created_at.isoformat()
        }