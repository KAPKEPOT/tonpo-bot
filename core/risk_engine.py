# fx/core/risk_engine.py
import math
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal
import logging

from core.models import TradeSignal, CalculatedTrade
from core.exceptions import RiskError
from config.constants import JPY_SYMBOLS
from config.settings import settings

logger = logging.getLogger(__name__)


class PositionSizeCalculator:
    """
    Calculates position sizes based on risk parameters
    """
    
    def __init__(self):
        self.pip_values = {
            'forex': 10.0,  # $10 per pip for standard lot
            'xauusd': 1.0,  # $1 per pip for gold
            'xagusd': 0.1,  # $0.1 per pip for silver
            'indices': 1.0,  # Varies by index
            'crypto': 1.0    # Varies by crypto
        }
    
    def calculate(
        self,
        balance: float,
        risk_percentage: float,
        stop_loss_pips: int,
        symbol: str,
        max_size: Optional[float] = None,
        account_currency: str = 'USD'
    ) -> float:
        """
        Calculate position size based on risk
        
        Formula: (Balance * Risk%) / (Stop Loss Pips * Pip Value)
        
        Args:
            balance: Account balance in account currency
            risk_percentage: Risk per trade as decimal (0.01 = 1%)
            stop_loss_pips: Stop loss distance in pips
            symbol: Trading symbol (for pip value)
            max_size: Maximum allowed position size
            account_currency: Account currency (USD, EUR, etc.)
        
        Returns:
            Position size in lots
        """
        if balance <= 0:
            raise RiskError("Balance must be positive")
        
        if risk_percentage <= 0 or risk_percentage > 0.1:
            raise RiskError(f"Risk percentage must be between 0.001 and 0.1, got {risk_percentage}")
        
        if stop_loss_pips <= 0:
            raise RiskError(f"Stop loss pips must be positive, got {stop_loss_pips}")
        
        # Get pip value for symbol
        pip_value = self._get_pip_value(symbol)
        
        # Calculate risk amount in account currency
        risk_amount = balance * risk_percentage
        
        # Calculate position size
        # Position Size = Risk Amount / (Stop Loss Pips * Pip Value)
        raw_size = risk_amount / (stop_loss_pips * pip_value)
        
        # Round to standard lot increments (0.01 for most brokers)
        position_size = math.floor(raw_size * 100) / 100
        
        # Apply maximum size limit
        if max_size and position_size > max_size:
            logger.info(f"Position size {position_size} capped at {max_size}")
            position_size = max_size
        
        # Ensure minimum size
        min_size = 0.01
        if position_size < min_size:
            logger.warning(f"Position size {position_size} below minimum, using {min_size}")
            position_size = min_size
        
        return position_size
    
    def calculate_for_multiple_tps(
        self,
        balance: float,
        risk_percentage: float,
        stop_loss_pips: int,
        take_profit_pips: List[int],
        symbol: str,
        max_size: Optional[float] = None
    ) -> Tuple[float, List[float]]:
        """
        Calculate position size for multiple take profits
        Returns total position size and individual trade sizes
        """
        total_size = self.calculate(
            balance=balance,
            risk_percentage=risk_percentage,
            stop_loss_pips=stop_loss_pips,
            symbol=symbol,
            max_size=max_size
        )
        
        # Split equally among TPs
        if len(take_profit_pips) > 1:
            individual_sizes = [total_size / len(take_profit_pips)] * len(take_profit_pips)
        else:
            individual_sizes = [total_size]
        
        return total_size, individual_sizes
    
    def calculate_required_margin(
        self,
        position_size: float,
        symbol: str,
        price: float,
        leverage: int = 100
    ) -> float:
        """
        Calculate required margin for a position
        """
        # Simplified margin calculation
        # In reality, this depends on broker, symbol, etc.
        contract_size = 100000  # 1 lot = 100,000 units
        notional_value = position_size * contract_size * price
        margin = notional_value / leverage
        
        return margin
    
    def _get_pip_value(self, symbol: str) -> float:
        """
        Get pip value in account currency for 1 standard lot
        """
        if 'XAU' in symbol or 'GOLD' in symbol:
            return self.pip_values['xauusd']
        elif 'XAG' in symbol or 'SILVER' in symbol:
            return self.pip_values['xagusd']
        elif 'JPY' in symbol:
            # For JPY pairs, pip value is approximately 1000/price
            # This is simplified - actual value depends on current price
            return 9.0  # Approximate for USDJPY around 110
        elif 'BTC' in symbol or 'ETH' in symbol:
            return self.pip_values['crypto']
        else:
            return self.pip_values['forex']


class RiskRewardCalculator:
    """
    Calculates risk/reward ratios and other metrics
    """
    
    @staticmethod
    def calculate_rr(entry: float, stop_loss: float, take_profits: List[float]) -> Dict[str, float]:
        """
        Calculate risk/reward ratio
        """
        risk = abs(entry - stop_loss)
        if risk == 0:
            return {
                'rr_ratio': 0.0,
                'risk': 0.0,
                'avg_reward': 0.0,
                'total_reward': 0.0,
                'reward_per_tp': []
            }
        
        # Calculate reward for each TP
        rewards = [abs(tp - entry) for tp in take_profits]
        total_reward = sum(rewards)
        avg_reward = total_reward / len(take_profits)
        
        # Calculate individual RR ratios
        rr_per_tp = [reward / risk for reward in rewards]
        
        return {
            'rr_ratio': avg_reward / risk,
            'risk': risk,
            'avg_reward': avg_reward,
            'total_reward': total_reward,
            'reward_per_tp': rewards,
            'rr_per_tp': rr_per_tp
        }
    
    @staticmethod
    def calculate_pips(price1: float, price2: float, symbol: str) -> int:
        """
        Calculate difference in pips between two prices
        """
        multiplier = RiskRewardCalculator._get_pip_multiplier(symbol)
        return abs(int(round((price1 - price2) / multiplier)))
    
    @staticmethod
    def calculate_monetary_risk(
        position_size: float,
        stop_loss_pips: int,
        symbol: str,
        account_currency: str = 'USD'
    ) -> float:
        """
        Calculate monetary risk in account currency
        """
        pip_value = RiskRewardCalculator._get_pip_value_in_currency(symbol, account_currency)
        return position_size * pip_value * stop_loss_pips
    
    @staticmethod
    def calculate_monetary_reward(
        position_size: float,
        take_profit_pips: List[int],
        symbol: str,
        split_position: bool = True,
        account_currency: str = 'USD'
    ) -> List[float]:
        """
        Calculate monetary reward for each TP
        """
        pip_value = RiskRewardCalculator._get_pip_value_in_currency(symbol, account_currency)
        
        if split_position and len(take_profit_pips) > 1:
            size_per_tp = position_size / len(take_profit_pips)
            return [size_per_tp * pip_value * pips for pips in take_profit_pips]
        else:
            return [position_size * pip_value * pips for pips in take_profit_pips]
    
    @staticmethod
    def _get_pip_multiplier(symbol: str) -> float:
        """Get pip multiplier for symbol"""
        if symbol == 'XAUUSD':
            return 0.1
        elif symbol == 'XAGUSD':
            return 0.001
        elif any(jpy in symbol for jpy in JPY_SYMBOLS):
            return 0.01
        else:
            return 0.0001
    
    @staticmethod
    def _get_pip_value_in_currency(symbol: str, currency: str = 'USD') -> float:
        """
        Get pip value for 1 standard lot in account currency
        Simplified - actual value depends on current exchange rates
        """
        base_pip_value = 10.0  # $10 per pip for standard lot
        
        if currency == 'USD':
            return base_pip_value
        elif currency == 'EUR':
            return base_pip_value * 0.85  # Approximate EUR/USD
        elif currency == 'GBP':
            return base_pip_value * 0.75  # Approximate GBP/USD
        else:
            return base_pip_value


class RiskEngine:
    """
    Main risk engine - orchestrates all risk calculations
    """
    
    def __init__(self):
        self.position_calculator = PositionSizeCalculator()
        self.rr_calculator = RiskRewardCalculator()
        
        # Default limits
        self.max_risk_per_trade = settings.MAX_RISK_FACTOR
        self.min_risk_per_trade = settings.MIN_RISK_FACTOR
        self.default_risk = settings.DEFAULT_RISK_FACTOR
    
    def calculate_trade(
        self,
        signal: TradeSignal,
        balance: float,
        risk_factor: Optional[float] = None,
        user_settings: Optional[Dict[str, Any]] = None
    ) -> CalculatedTrade:
        """
        Calculate all trade metrics
        """
        # Determine risk factor
        risk = risk_factor or self.default_risk
        
        # Apply user settings overrides
        if user_settings:
            # Check for symbol-specific override
            symbol_overrides = user_settings.get('symbol_risk_overrides', {})
            if signal.symbol in symbol_overrides:
                risk = symbol_overrides[signal.symbol]
                logger.info(f"Using symbol override for {signal.symbol}: {risk}")
            
            # Apply global limits
            max_risk = user_settings.get('max_risk_per_trade', self.max_risk_per_trade)
            if risk > max_risk:
                logger.warning(f"Risk {risk} capped at {max_risk}")
                risk = max_risk
            
            min_risk = user_settings.get('min_risk_per_trade', self.min_risk_per_trade)
            if risk < min_risk:
                logger.warning(f"Risk {risk} raised to minimum {min_risk}")
                risk = min_risk
        
        # Calculate stop loss in pips
        if not signal.entry:
            raise RiskError("Cannot calculate pips without entry price")
        
        stop_loss_pips = self.rr_calculator.calculate_pips(
            signal.entry, signal.stop_loss, signal.symbol
        )
        
        # Calculate take profits in pips
        take_profit_pips = []
        for tp in signal.take_profits:
            pips = self.rr_calculator.calculate_pips(tp, signal.entry, signal.symbol)
            take_profit_pips.append(pips)
        
        # Calculate position size
        max_size = user_settings.get('max_position_size') if user_settings else None
        position_size = self.position_calculator.calculate(
            balance=balance,
            risk_percentage=risk,
            stop_loss_pips=stop_loss_pips,
            symbol=signal.symbol,
            max_size=max_size
        )
        
        # Calculate monetary values
        potential_loss = self.rr_calculator.calculate_monetary_risk(
            position_size, stop_loss_pips, signal.symbol
        )
        
        # Determine if position should be split for multiple TPs
        split_position = user_settings.get('split_multiple_tps', True) if user_settings else True
        
        potential_profits = self.rr_calculator.calculate_monetary_reward(
            position_size, take_profit_pips, signal.symbol, split_position
        )
        
        # Calculate risk/reward
        rr_info = self.rr_calculator.calculate_rr(
            signal.entry, signal.stop_loss, signal.take_profits
        )
        
        # Create calculated trade
        calculated = CalculatedTrade(
            signal=signal,
            balance=balance,
            position_size=position_size,
            stop_loss_pips=stop_loss_pips,
            take_profit_pips=take_profit_pips,
            potential_loss=potential_loss,
            potential_profits=potential_profits,
            risk_percentage=risk * 100,
            risk_reward_ratio=rr_info['rr_ratio']
        )
        
        logger.info(f"Calculated trade: {calculated}")
        
        return calculated
    
    def validate_trade(
        self,
        calculated: CalculatedTrade,
        user_settings: Dict[str, Any]
    ) -> Tuple[bool, List[str]]:
        """
        Validate if calculated trade meets user constraints
        """
        errors = []
        
        # Check minimum stop loss distance
        min_sl = user_settings.get('min_stop_loss_pips', 10)
        if calculated.stop_loss_pips < min_sl:
            errors.append(f"Stop loss too tight: {calculated.stop_loss_pips} < {min_sl} pips")
        
        # Check maximum stop loss distance
        max_sl = user_settings.get('max_stop_loss_pips', 500)
        if calculated.stop_loss_pips > max_sl:
            errors.append(f"Stop loss too wide: {calculated.stop_loss_pips} > {max_sl} pips")
        
        # Check minimum take profit distances
        min_tp = user_settings.get('min_take_profit_pips', 10)
        for i, tp_pips in enumerate(calculated.take_profit_pips):
            if tp_pips < min_tp:
                errors.append(f"TP{i+1} too tight: {tp_pips} < {min_tp} pips")
        
        # Check maximum take profit distances
        max_tp = user_settings.get('max_take_profit_pips', 1000)
        for i, tp_pips in enumerate(calculated.take_profit_pips):
            if tp_pips > max_tp:
                errors.append(f"TP{i+1} too wide: {tp_pips} > {max_tp} pips")
        
        # Check minimum risk/reward
        min_rr = user_settings.get('min_risk_reward', 1.0)
        if calculated.risk_reward_ratio < min_rr:
            errors.append(f"Risk/reward too low: {calculated.risk_reward_ratio:.2f} < {min_rr}")
        
        # Check maximum risk per trade
        max_risk_pct = user_settings.get('max_risk_per_trade', 5.0)
        if calculated.risk_percentage > max_risk_pct:
            errors.append(f"Risk {calculated.risk_percentage:.1f}% > max {max_risk_pct}%")
        
        # Check maximum position size
        max_size = user_settings.get('max_position_size', 100.0)
        if calculated.position_size > max_size:
            errors.append(f"Position size {calculated.position_size} > max {max_size}")
        
        return len(errors) == 0, errors
    
    def suggest_adjustments(
        self,
        signal: TradeSignal,
        balance: float,
        user_settings: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Suggest adjustments to meet user constraints
        """
        suggestions = {}
        
        # Try different risk levels
        risk_levels = [0.005, 0.01, 0.015, 0.02, 0.025, 0.03]
        valid_trades = []
        
        for risk in risk_levels:
            try:
                calculated = self.calculate_trade(
                    signal=signal,
                    balance=balance,
                    risk_factor=risk,
                    user_settings=user_settings
                )
                
                is_valid, errors = self.validate_trade(calculated, user_settings)
                
                if is_valid:
                    valid_trades.append({
                        'risk': risk * 100,
                        'position_size': calculated.position_size,
                        'potential_loss': calculated.potential_loss,
                        'potential_profit': calculated.total_potential_profit,
                        'rr_ratio': calculated.risk_reward_ratio
                    })
            except Exception as e:
                logger.debug(f"Risk level {risk} failed: {e}")
        
        if valid_trades:
            # Find the highest risk that works (more aggressive)
            best_trade = max(valid_trades, key=lambda x: x['risk'])
            suggestions['recommended'] = best_trade
            suggestions['alternatives'] = valid_trades
        
        return suggestions


class DrawdownCalculator:
    """
    Calculates drawdown and risk of ruin
    """
    
    @staticmethod
    def calculate_max_drawdown(equity_curve: List[float]) -> Dict[str, float]:
        """
        Calculate maximum drawdown from equity curve
        """
        if not equity_curve:
            return {'max_drawdown': 0, 'max_drawdown_pct': 0}
        
        peak = equity_curve[0]
        max_drawdown = 0
        max_drawdown_pct = 0
        
        for value in equity_curve[1:]:
            if value > peak:
                peak = value
            else:
                drawdown = peak - value
                drawdown_pct = (drawdown / peak) * 100
                
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
                    max_drawdown_pct = drawdown_pct
        
        return {
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct
        }
    
    @staticmethod
    def calculate_risk_of_ruin(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        initial_capital: float
    ) -> float:
        """
        Calculate risk of ruin using simplified formula
        """
        if win_rate <= 0 or win_rate >= 1:
            return 1.0
        
        # Calculate edge
        edge = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        if edge <= 0:
            return 1.0  # Certain ruin if no edge
        
        # Simplified risk of ruin formula
        # RoR = ((1 - edge) / (1 + edge))^(initial_capital / avg_loss)
        a = (1 - edge) / (1 + edge)
        if a <= 0:
            return 0.0
        
        risk_of_ruin = a ** (initial_capital / avg_loss)
        
        return min(risk_of_ruin, 1.0)
    
    @staticmethod
    def calculate_optimal_fraction(
        win_rate: float,
        avg_win: float,
        avg_loss: float
    ) -> float:
        """
        Calculate Kelly Criterion optimal fraction
        """
        if win_rate <= 0 or win_rate >= 1:
            return 0
        
        # Kelly formula: f* = (p * b - q) / b
        # where p = win rate, q = loss rate, b = win/loss ratio
        b = avg_win / avg_loss if avg_loss > 0 else 0
        q = 1 - win_rate
        
        if b <= 0:
            return 0
        
        kelly_fraction = (win_rate * b - q) / b
        
        # Kelly can suggest very aggressive sizing
        # Common to use fractional Kelly (25-50%)
        return max(0, min(kelly_fraction * 0.25, 0.25))  # Cap at 25%