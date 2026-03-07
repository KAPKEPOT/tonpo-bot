# fx/core/parser.py
import re
import json
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import logging

from core.models import TradeSignal
from core.exceptions import SignalParseError, InvalidSymbolError
from config.constants import OrderType, JPY_SYMBOLS
from config.settings import settings

logger = logging.getLogger(__name__)


class SignalParser:
    """
    Parses raw text signals from various sources into structured TradeSignal objects
    Supports multiple formats: standard, compact, JSON, and custom formats
    """
    
    def __init__(self):
        self.allowed_symbols = settings.ALLOWED_SYMBOLS
        self.supported_formats = ['standard', 'compact', 'json', 'mt4', 'tradingview']
        
    def parse(self, text: str, source: str = 'telegram') -> TradeSignal:
        """
        Main parse method - tries all available parsers
        """
        if not text or not text.strip():
            raise SignalParseError("Empty signal text")
        
        # Clean the text
        text = self._clean_text(text)
        
        # Try each parser in order
        errors = []
        
        # Try JSON first (most structured)
        try:
            return self._parse_json(text)
        except SignalParseError as e:
            errors.append(f"JSON parser failed: {e}")
        
        # Try standard format
        try:
            return self._parse_standard(text)
        except SignalParseError as e:
            errors.append(f"Standard parser failed: {e}")
        
        # Try compact format
        try:
            return self._parse_compact(text)
        except SignalParseError as e:
            errors.append(f"Compact parser failed: {e}")
        
        # Try MT4 format
        try:
            return self._parse_mt4(text)
        except SignalParseError as e:
            errors.append(f"MT4 parser failed: {e}")
        
        # Try TradingView format
        try:
            return self._parse_tradingview(text)
        except SignalParseError as e:
            errors.append(f"TradingView parser failed: {e}")
        
        # If we get here, all parsers failed
        error_msg = "\n".join(errors)
        raise SignalParseError(f"Could not parse signal with any known format:\n{error_msg}")
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize input text"""
        # Remove extra whitespace
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        return '\n'.join(lines)
    
    def _parse_json(self, text: str) -> TradeSignal:
        """
        Parse JSON format:
        {
            "order_type": "BUY",
            "symbol": "EURUSD",
            "entry": 1.1000,
            "stop_loss": 1.0950,
            "take_profits": [1.1050, 1.1100]
        }
        """
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise SignalParseError(f"Invalid JSON: {e}")
        
        # Validate required fields
        required = ['order_type', 'symbol', 'stop_loss', 'take_profits']
        missing = [f for f in required if f not in data]
        if missing:
            raise SignalParseError(f"Missing required fields: {missing}")
        
        # Parse order type
        try:
            order_type = OrderType(data['order_type'].title())
        except (ValueError, AttributeError):
            raise SignalParseError(f"Invalid order type: {data.get('order_type')}")
        
        # Validate symbol
        symbol = data['symbol'].upper()
        self._validate_symbol(symbol)
        
        # Parse entry (can be null for market orders)
        entry = data.get('entry')
        if entry is not None:
            try:
                entry = float(entry)
            except (ValueError, TypeError):
                raise SignalParseError(f"Invalid entry price: {entry}")
        
        # Parse stop loss
        try:
            stop_loss = float(data['stop_loss'])
        except (ValueError, TypeError):
            raise SignalParseError(f"Invalid stop loss: {data['stop_loss']}")
        
        # Parse take profits
        take_profits = []
        for tp in data['take_profits']:
            try:
                take_profits.append(float(tp))
            except (ValueError, TypeError):
                raise SignalParseError(f"Invalid take profit: {tp}")
        
        # Create signal
        signal = TradeSignal(
            order_type=order_type,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            metadata={'source': 'json', 'raw': text}
        )
        
        # Validate
        errors = signal.validate()
        if errors:
            raise SignalParseError(f"Invalid signal: {', '.join(errors)}")
        
        return signal
    
    def _parse_standard(self, text: str) -> TradeSignal:
        """
        Parse standard format:
        BUY/SELL [LIMIT/STOP] SYMBOL
        Entry PRICE or NOW
        SL PRICE
        TP1 PRICE
        TP2 PRICE (optional)
        """
        lines = text.split('\n')
        
        if len(lines) < 4:
            raise SignalParseError("Standard format requires at least 4 lines")
        
        # Parse first line: ORDER_TYPE SYMBOL
        first_line = lines[0].strip().upper()
        parts = first_line.split()
        
        if len(parts) < 2:
            raise SignalParseError("First line must contain order type and symbol")
        
        # Handle multi-word order types (e.g., "BUY LIMIT")
        if len(parts) >= 3 and parts[1] in ['LIMIT', 'STOP']:
            order_text = f"{parts[0]} {parts[1]}"
            symbol = parts[2]
        else:
            order_text = parts[0]
            symbol = parts[1]
        
        # Parse order type
        try:
            order_type = OrderType(order_text.title())
        except ValueError:
            raise SignalParseError(f"Invalid order type: {order_text}")
        
        # Validate symbol
        self._validate_symbol(symbol)
        
        # Parse entry line
        entry_line = lines[1].strip().upper()
        if 'NOW' in entry_line:
            entry = None  # Market order
        else:
            try:
                # Extract last word as price
                entry = float(entry_line.split()[-1])
            except (ValueError, IndexError):
                raise SignalParseError(f"Invalid entry price: {entry_line}")
        
        # Parse stop loss
        try:
            stop_loss = float(lines[2].strip().split()[-1])
        except (ValueError, IndexError):
            raise SignalParseError(f"Invalid stop loss: {lines[2]}")
        
        # Parse take profits (at least 1, max 2)
        take_profits = []
        for i in range(3, min(5, len(lines))):
            try:
                tp = float(lines[i].strip().split()[-1])
                take_profits.append(tp)
            except (ValueError, IndexError):
                break
        
        if not take_profits:
            raise SignalParseError("At least one take profit required")
        
        # Create signal
        signal = TradeSignal(
            order_type=order_type,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            metadata={'source': 'standard', 'raw': text}
        )
        
        # Validate
        errors = signal.validate()
        if errors:
            raise SignalParseError(f"Invalid signal: {', '.join(errors)}")
        
        return signal
    
    def _parse_compact(self, text: str) -> TradeSignal:
        """
        Parse compact format:
        BUY EURUSD 1.1000 SL 1.0950 TP1 1.1050 TP2 1.1100
        or
        BUY EURUSD SL 1.0950 TP1 1.1050 (market order)
        """
        text = text.upper().strip()
        
        # Pattern for compact format
        pattern = r'^(BUY|SELL|BUY\s+LIMIT|SELL\s+LIMIT|BUY\s+STOP|SELL\s+STOP)\s+(\w+)(?:\s+(\d+\.?\d*|NOW))?\s+SL\s+(\d+\.?\d*)(?:\s+TP1\s+(\d+\.?\d*))?(?:\s+TP2\s+(\d+\.?\d*))?$'
        
        match = re.match(pattern, text)
        if not match:
            raise SignalParseError("Invalid compact format")
        
        groups = match.groups()
        
        # Parse order type
        try:
            order_type = OrderType(groups[0].title())
        except ValueError:
            raise SignalParseError(f"Invalid order type: {groups[0]}")
        
        # Parse symbol
        symbol = groups[1]
        self._validate_symbol(symbol)
        
        # Parse entry
        entry_str = groups[2]
        if entry_str == 'NOW' or not entry_str:
            entry = None
        else:
            try:
                entry = float(entry_str)
            except ValueError:
                raise SignalParseError(f"Invalid entry: {entry_str}")
        
        # Parse stop loss
        try:
            stop_loss = float(groups[3])
        except (ValueError, TypeError):
            raise SignalParseError(f"Invalid stop loss: {groups[3]}")
        
        # Parse take profits
        take_profits = []
        if groups[4]:
            take_profits.append(float(groups[4]))
        if groups[5]:
            take_profits.append(float(groups[5]))
        
        if not take_profits:
            raise SignalParseError("At least one take profit required")
        
        # Create signal
        signal = TradeSignal(
            order_type=order_type,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            metadata={'source': 'compact', 'raw': text}
        )
        
        # Validate
        errors = signal.validate()
        if errors:
            raise SignalParseError(f"Invalid signal: {', '.join(errors)}")
        
        return signal
    
    def _parse_mt4(self, text: str) -> TradeSignal:
        """
        Parse MT4 Expert Advisor format:
        ORDER_TYPE_BUY SYMBOL VOLUME [at] PRICE SL TP [comment]
        """
        text = text.upper().strip()
        
        # Pattern for MT4 format
        pattern = r'^ORDER_TYPE_(BUY|SELL|BUY_LIMIT|SELL_LIMIT|BUY_STOP|SELL_STOP)\s+(\w+)\s+(\d+\.?\d*)(?:\s+AT\s+(\d+\.?\d*))?\s+SL\s+(\d+\.?\d*)\s+TP\s+(\d+\.?\d*)(?:\s+(\w+))?$'
        
        match = re.match(pattern, text)
        if not match:
            raise SignalParseError("Invalid MT4 format")
        
        groups = match.groups()
        
        # Map MT4 order types to our OrderType
        mt4_order_map = {
            'BUY': OrderType.BUY,
            'SELL': OrderType.SELL,
            'BUY_LIMIT': OrderType.BUY_LIMIT,
            'SELL_LIMIT': OrderType.SELL_LIMIT,
            'BUY_STOP': OrderType.BUY_STOP,
            'SELL_STOP': OrderType.SELL_STOP
        }
        
        order_type = mt4_order_map.get(groups[0])
        if not order_type:
            raise SignalParseError(f"Invalid MT4 order type: {groups[0]}")
        
        # Parse symbol
        symbol = groups[1]
        self._validate_symbol(symbol)
        
        # Volume is ignored in our model (we calculate based on risk)
        # Parse entry
        entry_str = groups[3]
        if entry_str:
            entry = float(entry_str)
        else:
            entry = None  # Market order
        
        # Parse stop loss
        try:
            stop_loss = float(groups[4])
        except (ValueError, TypeError):
            raise SignalParseError(f"Invalid stop loss: {groups[4]}")
        
        # Parse take profit (single TP in MT4 format)
        try:
            tp = float(groups[5])
            take_profits = [tp]
        except (ValueError, TypeError):
            raise SignalParseError(f"Invalid take profit: {groups[5]}")
        
        # Create signal
        signal = TradeSignal(
            order_type=order_type,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            metadata={'source': 'mt4', 'raw': text}
        )
        
        # Validate
        errors = signal.validate()
        if errors:
            raise SignalParseError(f"Invalid signal: {', '.join(errors)}")
        
        return signal
    
    def _parse_tradingview(self, text: str) -> TradeSignal:
        """
        Parse TradingView alert format:
        {{strategy.order.action}} {{ticker}} at {{strategy.order.price}}
        SL: {{strategy.order.stop_loss}} TP: {{strategy.order.take_profit}}
        """
        lines = text.split('\n')
        
        if len(lines) < 2:
            raise SignalParseError("TradingView format requires at least 2 lines")
        
        # Parse first line: action symbol at price
        first_line = lines[0].strip()
        parts = first_line.split()
        
        if len(parts) < 3:
            raise SignalParseError("Invalid TradingView first line")
        
        # Extract action (buy/sell)
        action = parts[0].upper()
        if action not in ['BUY', 'SELL']:
            raise SignalParseError(f"Invalid action: {action}")
        
        # Extract symbol
        symbol = parts[1].upper()
        self._validate_symbol(symbol)
        
        # Check if price is specified
        entry = None
        if len(parts) >= 4 and parts[2].lower() == 'at':
            try:
                entry = float(parts[3])
            except ValueError:
                pass
        
        # Parse second line: SL and TP
        second_line = lines[1].upper()
        sl_match = re.search(r'SL:?\s*(\d+\.?\d*)', second_line)
        tp_match = re.search(r'TP:?\s*(\d+\.?\d*)', second_line)
        
        if not sl_match:
            raise SignalParseError("Stop loss not found in TradingView format")
        
        try:
            stop_loss = float(sl_match.group(1))
        except ValueError:
            raise SignalParseError(f"Invalid stop loss: {sl_match.group(1)}")
        
        take_profits = []
        if tp_match:
            try:
                take_profits.append(float(tp_match.group(1)))
            except ValueError:
                pass
        
        if not take_profits:
            raise SignalParseError("Take profit not found in TradingView format")
        
        # Determine order type
        if entry:
            order_type = OrderType.BUY_LIMIT if action == 'BUY' else OrderType.SELL_LIMIT
        else:
            order_type = OrderType.BUY if action == 'BUY' else OrderType.SELL
        
        # Create signal
        signal = TradeSignal(
            order_type=order_type,
            symbol=symbol,
            entry=entry,
            stop_loss=stop_loss,
            take_profits=take_profits,
            metadata={'source': 'tradingview', 'raw': text}
        )
        
        # Validate
        errors = signal.validate()
        if errors:
            raise SignalParseError(f"Invalid signal: {', '.join(errors)}")
        
        return signal
    
    def _validate_symbol(self, symbol: str) -> None:
        """Validate symbol against allowed list"""
        if symbol not in self.allowed_symbols:
            raise InvalidSymbolError(f"Symbol {symbol} is not allowed. Allowed: {', '.join(self.allowed_symbols[:10])}...")


class SignalValidator:
    """
    Validates signals against user settings and market conditions
    """
    
    def __init__(self, user_settings: Optional[Dict[str, Any]] = None):
        self.user_settings = user_settings or {}
    
    def validate_for_user(self, signal: TradeSignal, user_id: int) -> Tuple[bool, List[str]]:
        """
        Validate if signal is acceptable for a specific user
        """
        errors = []
        
        # Check if user exists and is active (would need user repo)
        # This would be implemented with database access
        
        # Check symbol restrictions
        allowed_symbols = self.user_settings.get('allowed_symbols', [])
        blocked_symbols = self.user_settings.get('blocked_symbols', [])
        
        if allowed_symbols and signal.symbol not in allowed_symbols:
            errors.append(f"Symbol {signal.symbol} not in allowed list")
        
        if blocked_symbols and signal.symbol in blocked_symbols:
            errors.append(f"Symbol {signal.symbol} is blocked")
        
        # Check risk limits
        max_risk = self.user_settings.get('max_risk_per_trade', 0.05)
        if signal.metadata.get('risk_percentage', 0) > max_risk:
            errors.append(f"Risk exceeds maximum allowed ({max_risk*100}%)")
        
        # Check position size limits
        max_size = self.user_settings.get('max_position_size', 10.0)
        if signal.metadata.get('position_size', 0) > max_size:
            errors.append(f"Position size exceeds maximum ({max_size})")
        
        return len(errors) == 0, errors
    
    def validate_market_conditions(self, signal: TradeSignal, market_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate signal against current market conditions
        """
        errors = []
        
        # Check spread
        max_spread = self.user_settings.get('max_spread')
        if max_spread and market_data.get('spread', 0) > max_spread:
            errors.append(f"Spread too high: {market_data['spread']} > {max_spread}")
        
        # Check volatility
        max_volatility = self.user_settings.get('max_volatility')
        if max_volatility and market_data.get('volatility', 0) > max_volatility:
            errors.append(f"Volatility too high: {market_data['volatility']} > {max_volatility}")
        
        # Check time restrictions
        trading_hours = self.user_settings.get('trading_hours')
        if trading_hours:
            current_hour = datetime.utcnow().hour
            if current_hour not in trading_hours:
                errors.append(f"Trading not allowed at {current_hour}:00 UTC")
        
        return len(errors) == 0, errors


class SignalEnricher:
    """
    Adds additional information to signals
    """
    
    def __init__(self):
        pass
    
    def add_pip_values(self, signal: TradeSignal) -> Dict[str, Any]:
        """Calculate pip values for SL and TPs"""
        # Determine pip multiplier
        multiplier = self._get_pip_multiplier(signal.symbol)
        
        result = {
            'pip_multiplier': multiplier,
            'sl_pips': None,
            'tp_pips': []
        }
        
        if signal.entry:
            result['sl_pips'] = abs(signal.stop_loss - signal.entry) / multiplier
            for tp in signal.take_profits:
                result['tp_pips'].append(abs(tp - signal.entry) / multiplier)
        
        return result
    
    def add_risk_reward(self, signal: TradeSignal) -> Dict[str, float]:
        """Calculate risk/reward ratio"""
        if not signal.entry:
            return {'rr_ratio': None, 'risk': None, 'avg_reward': None}
        
        risk = abs(signal.entry - signal.stop_loss)
        if risk == 0:
            return {'rr_ratio': 0, 'risk': 0, 'avg_reward': 0}
        
        # Average reward for multiple TPs
        total_reward = sum(abs(tp - signal.entry) for tp in signal.take_profits)
        avg_reward = total_reward / len(signal.take_profits)
        
        return {
            'rr_ratio': avg_reward / risk,
            'risk': risk,
            'avg_reward': avg_reward,
            'total_reward': total_reward
        }
    
    def add_market_info(self, signal: TradeSymbol, market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Add market information to signal"""
        return {
            'current_price': market_data.get('price'),
            'spread': market_data.get('spread'),
            'volatility': market_data.get('volatility'),
            'session': market_data.get('session'),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _get_pip_multiplier(self, symbol: str) -> float:
        """Get pip multiplier for symbol"""
        if symbol == 'XAUUSD':
            return 0.1
        elif symbol == 'XAGUSD':
            return 0.001
        elif any(jpy in symbol for jpy in JPY_SYMBOLS):
            return 0.01
        else:
            return 0.0001


class SignalNormalizer:
    """
    Normalizes signals to standard format
    """
    
    @staticmethod
    def normalize_symbol(symbol: str) -> str:
        """Normalize symbol to standard format"""
        return symbol.upper().strip()
    
    @staticmethod
    def normalize_price(price: float, digits: int = 5) -> float:
        """Normalize price to standard decimal places"""
        return round(price, digits)
    
    @staticmethod
    def normalize_order_type(order_type: str) -> OrderType:
        """Normalize order type string to enum"""
        order_map = {
            'B': OrderType.BUY,
            'S': OrderType.SELL,
            'BL': OrderType.BUY_LIMIT,
            'SL': OrderType.SELL_LIMIT,
            'BS': OrderType.BUY_STOP,
            'SS': OrderType.SELL_STOP,
            'BUY': OrderType.BUY,
            'SELL': OrderType.SELL,
            'BUYLIMIT': OrderType.BUY_LIMIT,
            'SELLLIMIT': OrderType.SELL_LIMIT,
            'BUYSTOP': OrderType.BUY_STOP,
            'SELLSTOP': OrderType.SELL_STOP
        }
        return order_map.get(order_type.upper().replace(' ', ''), OrderType.BUY)