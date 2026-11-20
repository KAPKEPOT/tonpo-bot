from core.exceptions import RiskError
from core.risk_engine import RiskEngine

class RiskService:
    def __init__(self):
        self._engine = RiskEngine()

    def calculate_trade(self, signal, balance, risk_factor=None,
                        user_settings=None, reference_price=None):
        return self._engine.calculate_trade(signal, balance, risk_factor,
                                            user_settings, reference_price)

    def validate_trade_parameters(self, signal, balance, user_settings):
        if balance <= 0:
            return False, ["Insufficient balance"]
        try:
            calculated = self._engine.calculate_trade(signal, balance,
                                                      user_settings=user_settings)
        except RiskError as e:
            return False, [str(e)]
        return self._engine.validate_trade(calculated, user_settings)