# core/pips.py
def base_symbol(symbol: str) -> str:
    return symbol.upper()[:6]   # 6-char FX and metals; index and crypto need their own rule

def pip_size(symbol: str) -> float:
    """Price distance of one pip."""
    s = base_symbol(symbol)
    if s == 'XAUUSD': return 0.1
    if s == 'XAGUSD': return 0.001
    if 'JPY' in s:    return 0.01
    return 0.0001