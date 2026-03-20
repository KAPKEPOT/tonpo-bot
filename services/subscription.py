# fx/services/subscription.py
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
import logging
from sqlalchemy.orm import Session

from database.models import User, SubscriptionPlan
from database.repositories import UserRepository
from config.settings import settings

logger = logging.getLogger(__name__)


class SubscriptionError(Exception):
    """Raised when subscription operations fail"""
    pass


class SubscriptionService:
    """
    Manages user subscriptions and plan limits
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.user_repo = UserRepository(db_session)
        self._plans_cache = None
        self._plans_cache_time = None
    
    def get_plan(self, tier: str) -> Optional[SubscriptionPlan]:
        """Get subscription plan by tier"""
        return self.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.tier == tier
        ).first()
    
    def get_all_plans(self, refresh: bool = False) -> List[SubscriptionPlan]:
        """Get all subscription plans with caching"""
        # Cache for 1 hour
        if (not self._plans_cache or refresh or 
            not self._plans_cache_time or 
            datetime.utcnow() - self._plans_cache_time > timedelta(hours=1)):
            
            self._plans_cache = self.db.query(SubscriptionPlan).all()
            self._plans_cache_time = datetime.utcnow()
        
        return self._plans_cache
    
    def get_user_plan(self, user_id: int) -> SubscriptionPlan:
        """Get user's current subscription plan"""
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            raise SubscriptionError("User not found")
        
        # Check if subscription expired
        if user.subscription_expiry and user.subscription_expiry < datetime.utcnow():
            # Downgrade to free
            user.subscription_tier = 'free'
            user.subscription_expiry = None
            self.db.commit()
            logger.info(f"User {user_id} downgraded to free plan (expired)")
        
        plan = self.get_plan(user.subscription_tier)
        if not plan:
            logger.error(f"Plan '{user.subscription_tier}' not found for user {user_id}, falling back to free")
            
            free_plan = self.get_plan('free')
            
            if not free_plan:
            	# Create default free plan if it doesn't exist
            	from database.models import SubscriptionPlan
            	free_plan = SubscriptionPlan(
            	    tier='free',
            	    name='Free',
            	    price_monthly=0,
            	    price_yearly=0,
            	    max_trades_per_day=10,
            	    max_position_size=1.0,
            	    max_symbols=30,
            	    supports_multiple_tps=False,
            	    supports_auto_trading=False,
            	    supports_api=False,
            	    support_priority='low',
            	    max_connections=1
            	)
            	self.db.add(free_plan)
            	self.db.commit()
            	
            # plan = self.get_plan('free')
            user.subscription_tier = 'free'
            self.db.commit()
            return free_plan
        
        return plan
    
    def check_trade_limit(self, user_id: int) -> Tuple[bool, Dict[str, Any]]:
        """Check if user has exceeded daily trade limit"""
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            return False, {"error": "User not found"}
        
        plan = self.get_user_plan(user_id)
        
        # Reset daily counter if new day
        if user.last_trade_date and user.last_trade_date.date() < datetime.utcnow().date():
            user.daily_trades = 0
            self.db.commit()
        
        # Check limit
        if user.daily_trades >= plan.max_trades_per_day:
            return False, {
                "limited": True,
                "current": user.daily_trades,
                "limit": plan.max_trades_per_day,
                "plan": plan.tier,
                "reset": datetime.utcnow().replace(hour=0, minute=0, second=0) + timedelta(days=1)
            }
        
        return True, {
            "limited": False,
            "current": user.daily_trades,
            "limit": plan.max_trades_per_day,
            "remaining": plan.max_trades_per_day - user.daily_trades
        }
    
    def check_position_size_limit(self, user_id: int, requested_size: float) -> Tuple[bool, str]:
        """Check if requested position size is within plan limits"""
        plan = self.get_user_plan(user_id)
        
        if requested_size > plan.max_position_size:
            return False, (f"Position size {requested_size} exceeds plan limit "
                          f"{plan.max_position_size}. Upgrade to increase limit.")
        
        return True, "OK"
    
    def check_feature_access(self, user_id: int, feature: str) -> bool:
        """Check if user has access to a specific feature"""
        plan = self.get_user_plan(user_id)
        
        feature_map = {
            'multiple_tps': plan.supports_multiple_tps,
            'auto_trading': plan.supports_auto_trading,
            'api_access': plan.supports_api,
            'priority_support': plan.support_priority == 'high'
        }
        
        return feature_map.get(feature, False)
    
    def increment_trade_count(self, user_id: int):
        """Increment user's daily trade count"""
        user = self.user_repo.get_by_telegram_id(user_id)
        if user:
            user.daily_trades += 1
            user.total_trades += 1
            user.last_trade_date = datetime.utcnow()
            self.db.commit()
    
    def upgrade_user(self, user_id: int, plan_tier: str, 
                    billing_period: str = 'monthly',
                    payment_method: str = 'crypto', 
                    payment_id: str = '',
                    tx_hash: str = '') -> Dict[str, Any]:
        """
        Upgrade user to a new plan.
        
        Args:
            billing_period: 'monthly' or 'yearly'
        """
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            raise SubscriptionError("User not found")
        
        plan = self.get_plan(plan_tier)
        if not plan:
            raise SubscriptionError(f"Plan {plan_tier} not found")
        
        # Calculate duration based on billing period
        if billing_period == 'yearly':
            duration_days = 365
            amount = float(plan.price_yearly)
        else:
            duration_days = 30
            amount = float(plan.price_monthly)
        
        # Update user
        old_plan = user.subscription_tier
        user.subscription_tier = plan_tier
        user.subscription_expiry = datetime.utcnow() + timedelta(days=duration_days)
        
        # Append to payment history (persisted JSON column)
        if user.payment_history is None:
            user.payment_history = []
        
        # SQLAlchemy won't detect in-place mutation of JSON — copy, modify, reassign
        history = list(user.payment_history)
        history.append({
            'date': datetime.utcnow().isoformat(),
            'plan': plan_tier,
            'billing_period': billing_period,
            'amount': amount,
            'currency': plan.currency or 'USD',
            'method': payment_method,
            'payment_id': payment_id,
            'tx_hash': tx_hash
        })
        user.payment_history = history
        
        self.db.commit()
        
        logger.info(f"User {user_id} upgraded from {old_plan} to {plan_tier} ({billing_period})")
        
        return {
            'success': True,
            'user_id': user_id,
            'old_plan': old_plan,
            'new_plan': plan_tier,
            'billing_period': billing_period,
            'duration_days': duration_days,
            'amount': amount,
            'expiry': user.subscription_expiry.isoformat(),
            'features': {
                'max_trades': plan.max_trades_per_day,
                'max_position_size': plan.max_position_size,
                'multiple_tps': plan.supports_multiple_tps,
                'auto_trading': plan.supports_auto_trading,
                'api_access': plan.supports_api
            }
        }
    
    def downgrade_user(self, user_id: int, reason: str = "expired") -> Dict[str, Any]:
        """Downgrade user to free plan"""
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            raise SubscriptionError("User not found")
        
        old_plan = user.subscription_tier
        user.subscription_tier = 'free'
        user.subscription_expiry = None
        
        self.db.commit()
        
        logger.info(f"User {user_id} downgraded from {old_plan} to free: {reason}")
        
        return {
            'success': True,
            'user_id': user_id,
            'old_plan': old_plan,
            'new_plan': 'free',
            'reason': reason
        }
    
    def get_expiring_soon(self, days: int = 7) -> List[Tuple[User, int]]:
        """Get users whose subscriptions expire soon"""
        cutoff = datetime.utcnow() + timedelta(days=days)
        
        users = self.db.query(User).filter(
            User.subscription_tier != 'free',
            User.subscription_expiry <= cutoff,
            User.subscription_expiry > datetime.utcnow()
        ).all()
        
        result = []
        for user in users:
            days_left = (user.subscription_expiry - datetime.utcnow()).days
            result.append((user, days_left))
        
        return result
    
    def get_expired(self) -> List[User]:
        """Get users with expired subscriptions"""
        return self.db.query(User).filter(
            User.subscription_tier != 'free',
            User.subscription_expiry < datetime.utcnow()
        ).all()
    
    def process_expired(self) -> int:
        """Process all expired subscriptions and downgrade to free"""
        expired = self.get_expired()
        count = 0
        
        for user in expired:
            try:
                self.downgrade_user(user.telegram_id, "expired")
                count += 1
            except Exception as e:
                logger.error(f"Failed to downgrade user {user.telegram_id}: {e}")
        
        return count
    
    def get_usage_stats(self, user_id: int) -> Dict[str, Any]:
    	"""Get usage statistics for user"""
    	user = self.user_repo.get_by_telegram_id(user_id)
    	
    	if not user:
    		raise SubscriptionError("User not found")
    	
    	plan = self.get_user_plan(user_id)
    	
    	if plan is None:
    		# Log this unexpected situation
    		logger.error(f"User {user_id} has no valid plan, using default stats")
    		
    		return {
    		    'plan': 'unknown',
    		    'expiry': None,
    		    'trades_today': user.daily_trades,
    		    'trade_limit': 0,
    		    'trade_usage_percent': 0,
    		    'total_trades': user.total_trades,
    		    'total_volume': user.total_volume,
    		    'features': {
    		        'multiple_tps': False,
    		        'auto_trading': False,
    		        'api_access': False
    		    }
    		}
    	
    	# Calculate usage percentages
    	trade_usage = (user.daily_trades / plan.max_trades_per_day * 100) if plan and plan.max_trades_per_day > 0 else 0
    	
    	return {
            'plan': plan.tier,
            'expiry': user.subscription_expiry.isoformat() if user.subscription_expiry else None,
            'trades_today': user.daily_trades,
            'trade_limit': plan.max_trades_per_day,
            'trade_usage_percent': round(trade_usage, 1),
            'total_trades': user.total_trades,
            'total_volume': user.total_volume,
            'features': {
                'multiple_tps': plan.supports_multiple_tps,
                'auto_trading': plan.supports_auto_trading,
                'api_access': plan.supports_api
            }
        }
    
    def get_plan_features(self, tier: str) -> Dict[str, Any]:
        """Get feature list for a plan"""
        plan = self.get_plan(tier)
        if not plan:
            return {}
        
        return {
            'name': plan.name,
            'tier': plan.tier,
            'price_monthly': float(plan.price_monthly),
            'price_yearly': float(plan.price_yearly),
            'max_trades_per_day': plan.max_trades_per_day,
            'max_position_size': plan.max_position_size,
            'max_symbols': plan.max_symbols,
            'supports_multiple_tps': plan.supports_multiple_tps,
            'supports_auto_trading': plan.supports_auto_trading,
            'supports_api': plan.supports_api,
            'support_priority': plan.support_priority,
            'max_connections': plan.max_connections,
            'features': plan.features or []
        }


class TrialService:
    """
    Manages free trials for new users
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.sub_service = SubscriptionService(db_session)
    
    def start_trial(self, user_id: int, days: int = 14) -> Dict[str, Any]:
        """Start a free trial for a user"""
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            raise SubscriptionError("User not found")
        
        # Check if user already had a trial
        if user.trial_used:
            return {
                'success': False,
                'message': 'Trial already used'
            }
        
        # Set trial plan
        user.subscription_tier = 'pro'  # Give them pro features
        user.subscription_expiry = datetime.utcnow() + timedelta(days=days)
        user.trial_used = True
        user.trial_start = datetime.utcnow()
        user.trial_end = datetime.utcnow() + timedelta(days=days)
        
        self.db.commit()
        
        logger.info(f"User {user_id} started {days}-day trial")
        
        return {
            'success': True,
            'message': f'Trial started for {days} days',
            'expiry': user.subscription_expiry.isoformat(),
            'features': self.sub_service.get_plan_features('pro')
        }
    
    def check_trial_eligibility(self, user_id: int) -> Dict[str, Any]:
        """Check if user is eligible for a trial"""
        user = self.db.query(User).filter(User.telegram_id == user_id).first()
        if not user:
            return {'eligible': False, 'reason': 'User not found'}
        
        if user.trial_used:
            return {'eligible': False, 'reason': 'Trial already used'}
        
        # Check account age (optional)
        account_age = datetime.utcnow() - user.created_at
        if account_age.days > 30:
            return {'eligible': False, 'reason': 'Account too old for trial'}
        
        return {
            'eligible': True,
            'trial_days': 14,
            'features': self.sub_service.get_plan_features('pro')
        }