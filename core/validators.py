# fx/core/validators.py
import re
from typing import Tuple, Optional, List, Dict, Any
from datetime import datetime, time
from decimal import Decimal

from config.constants import OrderType, REGEX_PATTERNS
from config.settings import settings


class SymbolValidator:
    """Validates trading symbols"""
    
    @staticmethod
    def validate(symbol: str) -> Tuple[bool, Optional[str]]:
        """
        Validate symbol format and existence
        """
        if not symbol:
            return False, "Symbol cannot be empty"
        
        symbol = symbol.upper().strip()
        
        # Check format
        if not re.match(REGEX_PATTERNS['symbol'], symbol):
            return False, f"Invalid symbol format: {symbol}"
        
        # Check if in allowed symbols
        if symbol not in settings.ALLOWED_SYMBOLS:
            return False, f"Symbol {symbol} not supported"
        
        return True, None
    
    @staticmethod
    def get_symbol_type(symbol: str) -> str:
        """Get symbol type (forex, commodity, etc.)"""
        symbol = symbol.upper()
        
        if symbol in ['XAUUSD', 'XAGUSD']:
            return 'commodity'
        elif symbol in ['BTCUSD', 'ETHUSD']:
            return 'crypto'
        elif 'JPY' in symbol:
            return 'forex_jpy'
        else:
            return 'forex'


class PriceValidator:
    """Validates price values"""
    
    @staticmethod
    def validate(price: float, min_price: float = 0, max_price: float = 100000) -> Tuple[bool, Optional[str]]:
        """
        Validate price value
        """
        if not isinstance(price, (int, float)):
            return False, "Price must be a number"
        
        if price <= min_price:
            return False, f"Price must be greater than {min_price}"
        
        if price > max_price:
            return False, f"Price cannot exceed {max_price}"
        
        return True, None
    
    @staticmethod
    def validate_spread(bid: float, ask: float, max_spread: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """
        Validate spread between bid and ask
        """
        if bid <= 0 or ask <= 0:
            return False, "Prices must be positive"
        
        if ask <= bid:
            return False, "Ask must be greater than bid"
        
        spread = ask - bid
        
        if max_spread and spread > max_spread:
            return False, f"Spread {spread:.5f} exceeds maximum {max_spread:.5f}"
        
        return True, None


class RiskValidator:
    """Validates risk parameters"""
    
    @staticmethod
    def validate_risk_percentage(risk: float) -> Tuple[bool, Optional[str]]:
        """
        Validate risk percentage
        """
        if not isinstance(risk, (int, float)):
            return False, "Risk must be a number"
        
        if risk < settings.MIN_RISK_FACTOR:
            return False, f"Risk must be at least {settings.MIN_RISK_FACTOR*100}%"
        
        if risk > settings.MAX_RISK_FACTOR:
            return False, f"Risk cannot exceed {settings.MAX_RISK_FACTOR*100}%"
        
        return True, None
    
    @staticmethod
    def validate_position_size(size: float, min_size: float = 0.01, max_size: float = 100) -> Tuple[bool, Optional[str]]:
        """
        Validate position size
        """
        if not isinstance(size, (int, float)):
            return False, "Position size must be a number"
        
        if size < min_size:
            return False, f"Position size must be at least {min_size}"
        
        if size > max_size:
            return False, f"Position size cannot exceed {max_size}"
        
        # Check if size is in valid increments (0.01 for most brokers)
        if abs(round(size * 100) - size * 100) > 0.0001:
            return False, "Position size must be in increments of 0.01"
        
        return True, None
    
    @staticmethod
    def validate_stop_loss(entry: float, sl: float, order_type: OrderType) -> Tuple[bool, Optional[str]]:
        """
        Validate stop loss relative to entry
        """
        if order_type in [OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP]:
            if sl >= entry:
                return False, "Stop loss must be below entry for BUY orders"
        else:
            if sl <= entry:
                return False, "Stop loss must be above entry for SELL orders"
        
        # Check minimum distance
        min_distance = 0.0001  # 1 pip minimum
        if abs(entry - sl) < min_distance:
            return False, "Stop loss too close to entry"
        
        return True, None
    
    @staticmethod
    def validate_take_profit(entry: float, tp: float, order_type: OrderType) -> Tuple[bool, Optional[str]]:
        """
        Validate take profit relative to entry
        """
        if order_type in [OrderType.BUY, OrderType.BUY_LIMIT, OrderType.BUY_STOP]:
            if tp <= entry:
                return False, "Take profit must be above entry for BUY orders"
        else:
            if tp >= entry:
                return False, "Take profit must be below entry for SELL orders"
        
        return True, None


class CredentialsValidator:
    """Validates MT5 credentials"""
    
    @staticmethod
    def validate_account_id(account_id: str) -> Tuple[bool, Optional[str]]:
        """
        Validate MT5 account ID format
        """
        if not account_id:
            return False, "Account ID cannot be empty"
        
        if not account_id.isdigit():
            return False, "Account ID must contain only digits"
        
        if len(account_id) < 5 or len(account_id) > 10:
            return False, "Account ID must be between 5 and 10 digits"
        
        return True, None
    
    @staticmethod
    def validate_server(server: str) -> Tuple[bool, Optional[str]]:
        """
        Validate MT5 server name
        """
        if not server:
            return False, "Server cannot be empty"
        
        if len(server) < 3 or len(server) > 100:
            return False, "Server name must be between 3 and 100 characters"
        
        # Common server patterns
        valid_patterns = [
            r'^[A-Za-z0-9\-\.]+$',  # Alphanumeric, hyphens, dots
            r'^[A-Za-z0-9\-]+(?:-(?:Demo|Real|Live|Main))?$'  # With suffix
        ]
        
        for pattern in valid_patterns:
            if re.match(pattern, server):
                return True, None
        
        return False, "Invalid server name format"
    
    @staticmethod
    def validate_password(password: str) -> Tuple[bool, Optional[str]]:
        """
        Basic password validation
        """
        if not password:
            return False, "Password cannot be empty"
        
        if len(password) < 4:
            return False, "Password too short"
        
        return True, None


class TimeValidator:
    """Validates time-related parameters"""
    
    @staticmethod
    def validate_trading_hours(hour: int) -> Tuple[bool, Optional[str]]:
        """
        Validate trading hour (0-23)
        """
        if not isinstance(hour, int):
            return False, "Hour must be an integer"
        
        if hour < 0 or hour > 23:
            return False, "Hour must be between 0 and 23"
        
        return True, None
    
    @staticmethod
    def validate_session(session: str) -> Tuple[bool, Optional[str]]:
        """
        Validate trading session
        """
        valid_sessions = ['asian', 'london', 'ny', 'all']
        if session.lower() not in valid_sessions:
            return False, f"Session must be one of: {', '.join(valid_sessions)}"
        
        return True, None
    
    @staticmethod
    def is_market_open(symbol: str, current_time: Optional[datetime] = None) -> bool:
        """
        Check if market is open for symbol
        Simplified - in reality, this depends on symbol and broker
        """
        if current_time is None:
            current_time = datetime.utcnow()
        
        # Forex is 24/5
        if current_time.weekday() >= 5:  # Saturday or Sunday
            return False
        
        # Check specific sessions
        hour = current_time.hour
        
        # Forex sessions
        if 'JPY' in symbol:
            # Asian session roughly
            return 0 <= hour <= 9
        elif 'EUR' in symbol or 'GBP' in symbol:
            # London session roughly
            return 7 <= hour <= 16
        elif 'USD' in symbol or 'CAD' in symbol:
            # NY session roughly
            return 13 <= hour <= 22
        
        return True


class InputValidator:
    """Validates general user input"""
    
    @staticmethod
    def validate_telegram_username(username: str) -> Tuple[bool, Optional[str]]:
        """
        Validate Telegram username format
        """
        if not username:
            return True, None  # Username is optional
        
        if not re.match(r'^[a-zA-Z0-9_]{5,32}$', username):
            return False, "Invalid username format"
        
        return True, None
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, Optional[str]]:
        """
        Validate email format
        """
        if not email:
            return False, "Email cannot be empty"
        
        if not re.match(REGEX_PATTERNS['email'], email):
            return False, "Invalid email format"
        
        return True, None
    
    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
        """
        Basic phone number validation
        """
        if not phone:
            return True, None  # Phone is optional
        
        # Remove common separators
        cleaned = re.sub(r'[\s\-\(\)]', '', phone)
        
        if not re.match(r'^\+?[1-9]\d{7,14}$', cleaned):
            return False, "Invalid phone number format"
        
        return True, None
    
    @staticmethod
    def validate_uuid(uuid_str: str) -> bool:
        """
        Validate UUID format
        """
        return bool(re.match(REGEX_PATTERNS['uuid'], uuid_str, re.I))


class TradeValidator:
    """
    Comprehensive trade validator combining multiple validators
    """
    
    def __init__(self):
        self.symbol_validator = SymbolValidator()
        self.price_validator = PriceValidator()
        self.risk_validator = RiskValidator()
    
    def validate_trade_parameters(
        self,
        symbol: str,
        entry: Optional[float],
        stop_loss: float,
        take_profits: List[float],
        order_type: OrderType,
        balance: Optional[float] = None
    ) -> List[str]:
        """
        Validate all trade parameters
        Returns list of validation errors
        """
        errors = []
        
        # Validate symbol
        valid, msg = self.symbol_validator.validate(symbol)
        if not valid:
            errors.append(msg)
        
        # Validate stop loss
        if entry:
            valid, msg = self.risk_validator.validate_stop_loss(entry, stop_loss, order_type)
            if not valid:
                errors.append(msg)
        
        # Validate take profits
        for i, tp in enumerate(take_profits):
            if entry:
                valid, msg = self.risk_validator.validate_take_profit(entry, tp, order_type)
                if not valid:
                    errors.append(f"TP{i+1}: {msg}")
        
        # Validate balance if provided
        if balance is not None and entry:
            # Check if balance is sufficient (simplified)
            required_margin = balance * 0.01  # Approximate
            if balance < required_margin:
                errors.append("Insufficient balance")
        
        return errors
    
    def validate_order_type(self, order_type: str) -> Tuple[bool, Optional[OrderType]]:
        """
        Validate and convert order type string
        """
        try:
            ot = OrderType(order_type.title())
            return True, ot
        except ValueError:
            return False, None