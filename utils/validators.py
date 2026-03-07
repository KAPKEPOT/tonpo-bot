# fx/utils/validators.py
import re
from typing import Tuple, Optional, Any, Dict, List
from datetime import datetime

from config.settings import settings
from utils.exceptions import ValidationError


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email address format
    """
    if not email:
        return False, "Email cannot be empty"
    
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(pattern, email):
        return False, "Invalid email format"
    
    return True, None


def validate_phone(phone: str) -> Tuple[bool, Optional[str]]:
    """
    Validate phone number format
    """
    if not phone:
        return True, None  # Phone is optional
    
    # Remove common separators
    cleaned = re.sub(r'[\s\-\(\)]', '', phone)
    
    pattern = r'^\+?[1-9]\d{7,14}$'
    if not re.match(pattern, cleaned):
        return False, "Invalid phone number format"
    
    return True, None


def validate_mt5_account(account_id: str) -> Tuple[bool, Optional[str]]:
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


def validate_mt5_server(server: str) -> Tuple[bool, Optional[str]]:
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


def validate_symbol(symbol: str) -> Tuple[bool, Optional[str]]:
    """
    Validate forex symbol
    """
    if not symbol:
        return False, "Symbol cannot be empty"
    
    symbol = symbol.upper()
    
    pattern = r'^[A-Z]{6}$'
    if not re.match(pattern, symbol):
        return False, f"Invalid symbol format: {symbol}"
    
    # Check if in allowed symbols
    if symbol not in settings.ALLOWED_SYMBOLS:
        return False, f"Symbol {symbol} is not supported"
    
    return True, None


def validate_price(price: float, min_price: float = 0, max_price: float = 100000) -> Tuple[bool, Optional[str]]:
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


def validate_risk_percentage(risk: float) -> Tuple[bool, Optional[str]]:
    """
    Validate risk percentage (as decimal, e.g., 0.01 = 1%)
    """
    if not isinstance(risk, (int, float)):
        return False, "Risk must be a number"
    
    if risk < 0.001 or risk > 0.1:
        return False, "Risk must be between 0.1% and 10%"
    
    return True, None


def validate_position_size(size: float, min_size: float = 0.01, max_size: float = 100) -> Tuple[bool, Optional[str]]:
    """
    Validate position size in lots
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


def validate_telegram_username(username: str) -> Tuple[bool, Optional[str]]:
    """
    Validate Telegram username format
    """
    if not username:
        return True, None  # Username is optional
    
    pattern = r'^[a-zA-Z0-9_]{5,32}$'
    if not re.match(pattern, username):
        return False, "Invalid username format"
    
    return True, None


def validate_uuid(uuid_str: str) -> bool:
    """
    Validate UUID format
    """
    pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(pattern, uuid_str, re.I))


def validate_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Validate URL format
    """
    if not url:
        return False, "URL cannot be empty"
    
    if not url.startswith(('http://', 'https://')):
        return False, "URL must start with http:// or https://"
    
    pattern = r'^https?:\/\/(?:www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b(?:[-a-zA-Z0-9()@:%_\+.~#?&\/=]*)$'
    if not re.match(pattern, url):
        return False, "Invalid URL format"
    
    return True, None


def validate_date(date_str: str, format: str = "%Y-%m-%d") -> Tuple[bool, Optional[datetime]]:
    """
    Validate date string format
    """
    try:
        date = datetime.strptime(date_str, format)
        return True, date
    except ValueError:
        return False, None


def validate_time_range(start_time: str, end_time: str) -> Tuple[bool, Optional[str]]:
    """
    Validate time range
    """
    time_format = "%H:%M"
    
    try:
        start = datetime.strptime(start_time, time_format)
        end = datetime.strptime(end_time, time_format)
        
        if start >= end:
            return False, "Start time must be before end time"
        
        return True, None
    except ValueError:
        return False, "Invalid time format. Use HH:MM (24-hour)"


def validate_password_strength(password: str) -> Tuple[bool, List[str]]:
    """
    Validate password strength
    """
    errors = []
    
    if len(password) < 8:
        errors.append("Password must be at least 8 characters long")
    
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter")
    
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter")
    
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number")
    
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character")
    
    return len(errors) == 0, errors


def validate_json_schema(data: Dict[str, Any], schema: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate data against JSON schema
    """
    errors = []
    
    for field, rules in schema.items():
        # Check required
        if rules.get('required', False) and field not in data:
            errors.append(f"Missing required field: {field}")
            continue
        
        if field in data:
            value = data[field]
            
            # Check type
            expected_type = rules.get('type')
            if expected_type and not isinstance(value, expected_type):
                errors.append(f"Field {field} must be of type {expected_type.__name__}")
            
            # Check min/max for numbers
            if isinstance(value, (int, float)):
                if 'min' in rules and value < rules['min']:
                    errors.append(f"Field {field} must be >= {rules['min']}")
                if 'max' in rules and value > rules['max']:
                    errors.append(f"Field {field} must be <= {rules['max']}")
            
            # Check pattern for strings
            if isinstance(value, str) and 'pattern' in rules:
                if not re.match(rules['pattern'], value):
                    errors.append(f"Field {field} does not match required pattern")
            
            # Check allowed values
            if 'allowed' in rules and value not in rules['allowed']:
                errors.append(f"Field {field} must be one of: {', '.join(map(str, rules['allowed']))}")
    
    return len(errors) == 0, errors


def validate_percentage(value: float, min_val: float = 0, max_val: float = 100) -> Tuple[bool, Optional[str]]:
    """
    Validate percentage value
    """
    if value < min_val or value > max_val:
        return False, f"Percentage must be between {min_val} and {max_val}"
    
    return True, None


def validate_integer(value: Any, min_val: Optional[int] = None, max_val: Optional[int] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate integer value
    """
    try:
        int_value = int(value)
    except (ValueError, TypeError):
        return False, "Value must be an integer"
    
    if min_val is not None and int_value < min_val:
        return False, f"Value must be at least {min_val}"
    
    if max_val is not None and int_value > max_val:
        return False, f"Value cannot exceed {max_val}"
    
    return True, None


def validate_float(value: Any, min_val: Optional[float] = None, max_val: Optional[float] = None) -> Tuple[bool, Optional[str]]:
    """
    Validate float value
    """
    try:
        float_value = float(value)
    except (ValueError, TypeError):
        return False, "Value must be a number"
    
    if min_val is not None and float_value < min_val:
        return False, f"Value must be at least {min_val}"
    
    if max_val is not None and float_value > max_val:
        return False, f"Value cannot exceed {max_val}"
    
    return True, None


def validate_boolean(value: Any) -> Tuple[bool, Optional[bool]]:
    """
    Validate and convert to boolean
    """
    if isinstance(value, bool):
        return True, value
    
    if isinstance(value, str):
        if value.lower() in ('true', 'yes', '1', 'on'):
            return True, True
        if value.lower() in ('false', 'no', '0', 'off'):
            return True, False
    
    if isinstance(value, (int, float)):
        return True, bool(value)
    
    return False, None


def validate_list(value: Any, item_type: Optional[type] = None) -> Tuple[bool, Optional[List]]:
    """
    Validate list and optionally its items
    """
    if not isinstance(value, list):
        return False, None
    
    if item_type:
        for item in value:
            if not isinstance(item, item_type):
                return False, None
    
    return True, value


def validate_dict(value: Any, schema: Optional[Dict] = None) -> Tuple[bool, Optional[Dict]]:
    """
    Validate dictionary
    """
    if not isinstance(value, dict):
        return False, None
    
    if schema:
        valid, errors = validate_json_schema(value, schema)
        if not valid:
            return False, None
    
    return True, value


def validate_not_empty(value: Any) -> Tuple[bool, Optional[str]]:
    """
    Validate value is not empty
    """
    if value is None:
        return False, "Value cannot be None"
    
    if isinstance(value, str) and not value.strip():
        return False, "Value cannot be empty string"
    
    if isinstance(value, (list, dict, tuple)) and len(value) == 0:
        return False, "Value cannot be empty collection"
    
    return True, None