# fx/database/repositories.py
"""
Repository pattern for database operations
Provides a clean abstraction over SQLAlchemy sessions
"""
from typing import Optional, List, Dict, Any, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func
from datetime import datetime, timedelta
import logging
from contextlib import contextmanager

from .models import (
    User, UserSettings, Trade, ConnectionLog, 
    Notification, SubscriptionPlan, ApiUsage
)

logger = logging.getLogger(__name__)


class BaseRepository:
    """Base repository with common methods"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def _safe_commit(self):
        """Safe commit with error handling"""
        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            logger.error(f"Database commit error: {e}")
            raise

    def _safe_query(self, query_fn):
        """Execute a query, recovering from broken transaction state"""
        try:
            return query_fn()
        except Exception as e:
            # Session may be in a failed transaction - rollback and retry once
            try:
                self.session.rollback()
                return query_fn()
            except Exception as retry_err:
                logger.error(f"Database query failed after rollback: {retry_err}")
                raise


class UserRepository(BaseRepository):
    """Repository for User operations"""
    
    def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        """Get user by Telegram ID"""
        return self._safe_query(
            lambda: self.session.query(User).filter(
                User.telegram_id == telegram_id
            ).first()
        )
    
    def get_by_uuid(self, uuid: str) -> Optional[User]:
        """Get user by UUID"""
        return self.session.query(User).filter(
            User.uuid == uuid
        ).first()
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by Telegram username"""
        return self.session.query(User).filter(
            User.telegram_username == username
        ).first()
    
    def create_user(self, telegram_id: int, **kwargs) -> User:
        """Create a new user"""
        # Check if user already exists
        existing = self.get_by_telegram_id(telegram_id)
        if existing:
            raise ValueError(f"User with telegram_id {telegram_id} already exists")
        
        # Create user
        user = User(telegram_id=telegram_id, **kwargs)
        self.session.add(user)
        self.session.flush()  # Get user.id
        
        # Create default settings
        settings = UserSettings(user_id=user.id)
        self.session.add(settings)
        
        self._safe_commit()
        logger.info(f"Created user {telegram_id} with ID {user.id}")
        
        return user
    
    def update_user(self, telegram_id: int, **kwargs) -> Optional[User]:
        """Update user fields"""
        user = self.get_by_telegram_id(telegram_id)
        if not user:
            return None
        
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        
        self._safe_commit()
        logger.info(f"Updated user {telegram_id}")
        
        return user
    
    def delete_user(self, telegram_id: int) -> bool:
        """Soft delete user (deactivate)"""
        user = self.get_by_telegram_id(telegram_id)
        if not user:
            return False
        
        user.is_active = False
        user.is_verified = False
        self._safe_commit()
        
        logger.info(f"Deactivated user {telegram_id}")
        return True
    
    def get_active_users(self, limit: int = 100) -> List[User]:
        """Get all active verified users"""
        return self.session.query(User).filter(
            User.is_active == True,
            User.is_verified == True,
            User.is_banned == False
        ).limit(limit).all()
    
    def get_users_needing_connection_check(self, minutes: int = 5) -> List[User]:
        """Get users whose connection hasn't been checked recently"""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        return self.session.query(User).filter(
            User.is_active == True,
            User.is_verified == True,
            or_(
                User.last_connected < cutoff,
                User.last_connected.is_(None)
            )
        ).all()
    
    def increment_trade_count(self, user_id: int) -> None:
        """Increment user's trade count"""
        user = self.session.query(User).filter(User.id == user_id).first()
        if user:
            user.total_trades += 1
            user.daily_trades += 1
            user.last_trade_date = datetime.utcnow()
            self.session.commit()
    
    def reset_daily_trades(self) -> int:
        """Reset daily trade counters for all users"""
        result = self.session.query(User).update(
            {User.daily_trades: 0}
        )
        self.session.commit()
        return result
    
    def get_users_by_subscription(self, tier: str) -> List[User]:
        """Get users by subscription tier"""
        return self.session.query(User).filter(
            User.subscription_tier == tier,
            User.is_active == True
        ).all()


class TradeRepository(BaseRepository):
    """Repository for Trade operations"""
    
    def create_trade(self, user_id: int, **kwargs) -> Trade:
        """Create a new trade record"""
        trade = Trade(user_id=user_id, **kwargs)
        self.session.add(trade)
        self._safe_commit()
        return trade
    
    def get_by_uuid(self, uuid: str) -> Optional[Trade]:
        """Get trade by UUID"""
        return self.session.query(Trade).filter(
            Trade.uuid == uuid
        ).first()
    
    def get_user_trades(self, user_id: int, limit: int = 50, offset: int = 0) -> List[Trade]:
        """Get trades for a specific user"""
        return self.session.query(Trade).filter(
            Trade.user_id == user_id
        ).order_by(
            desc(Trade.created_at)
        ).limit(limit).offset(offset).all()
    
    def get_recent_trades(self, hours: int = 24, status: Optional[str] = None) -> List[Trade]:
        """Get recent trades across all users"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        query = self.session.query(Trade).filter(Trade.created_at >= cutoff)
        
        if status:
            query = query.filter(Trade.status == status)
        
        return query.order_by(desc(Trade.created_at)).all()
    
    def check_duplicate(self, signal_hash: str, user_id: int, minutes: int = 5) -> bool:
        """Check if similar trade was executed recently"""
        cutoff = datetime.utcnow() - timedelta(minutes=minutes)
        existing = self.session.query(Trade).filter(
            Trade.signal_hash == signal_hash,
            Trade.user_id == user_id,
            Trade.created_at >= cutoff
        ).first()
        
        return existing is not None
    
    def update_trade_status(self, trade_uuid: str, status: str, **kwargs) -> Optional[Trade]:
        """Update trade status and other fields"""
        trade = self.get_by_uuid(trade_uuid)
        if not trade:
            return None
        
        trade.status = status
        for key, value in kwargs.items():
            if hasattr(trade, key):
                setattr(trade, key, value)
        
        self._safe_commit()
        return trade
    
    def get_user_stats(self, user_id: int, days: int = 30) -> Dict[str, Any]:
        """Get trading statistics for user"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        trades = self.session.query(Trade).filter(
            Trade.user_id == user_id,
            Trade.created_at >= cutoff,
            Trade.status == 'executed'
        ).all()
        
        total_trades = len(trades)
        if total_trades == 0:
            return {
                'total_trades': 0,
                'total_volume': 0,
                'avg_risk': 0,
                'most_traded': None
            }
        
        # Calculate stats
        total_volume = sum(float(t.position_size) for t in trades)
        avg_risk = sum(t.risk_percentage for t in trades) / total_trades
        
        # Most traded symbol
        symbols = {}
        for t in trades:
            symbols[t.symbol] = symbols.get(t.symbol, 0) + 1
        most_traded = max(symbols.items(), key=lambda x: x[1])[0] if symbols else None
        
        return {
            'total_trades': total_trades,
            'total_volume': total_volume,
            'avg_risk': avg_risk,
            'most_traded': most_traded,
            'trades_by_symbol': symbols
        }


class SettingsRepository(BaseRepository):
    """Repository for UserSettings operations"""
    
    def get_by_user_id(self, user_id: int) -> Optional[UserSettings]:
        """Get settings by user ID"""
        return self.session.query(UserSettings).filter(
            UserSettings.user_id == user_id
        ).first()
    
    def get_by_telegram_id(self, telegram_id: int) -> Optional[UserSettings]:
        """Get settings by Telegram ID"""
        return self.session.query(UserSettings).join(
            User, User.id == UserSettings.user_id
        ).filter(
            User.telegram_id == telegram_id
        ).first()
    
    def update_settings(self, user_id: int, **kwargs) -> Optional[UserSettings]:
        """Update user settings"""
        settings = self.get_by_user_id(user_id)
        if not settings:
            return None
        
        for key, value in kwargs.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        self._safe_commit()
        return settings
    
    def update_risk_override(self, user_id: int, symbol: str, risk_factor: float) -> Optional[UserSettings]:
        """Update risk override for a specific symbol"""
        settings = self.get_by_user_id(user_id)
        if not settings:
            return None
        
        overrides = settings.symbol_risk_overrides or {}
        overrides[symbol] = risk_factor
        settings.symbol_risk_overrides = overrides
        
        self._safe_commit()
        return settings
    
    def generate_api_key(self, user_id: int) -> Optional[str]:
        """Generate new API key for user"""
        settings = self.get_by_user_id(user_id)
        if not settings:
            return None
        
        import secrets
        settings.api_key = secrets.token_hex(32)
        settings.api_enabled = True
        self._safe_commit()
        
        return settings.api_key
    
    def revoke_api_key(self, user_id: int) -> bool:
        """Revoke user's API key"""
        settings = self.get_by_user_id(user_id)
        if not settings:
            return False
        
        settings.api_key = None
        settings.api_enabled = False
        self._safe_commit()
        
        return True


class NotificationRepository(BaseRepository):
    """Repository for Notification operations"""
    
    def create_notification(self, user_id: int, title: str, message: str, 
                       type: str = 'info', data: dict = None) -> Optional[Notification]:
        """Create a new notification"""
        from .models import User
        user_exists = self.session.query(User).filter(User.id == user_id).first()
        if not user_exists:
        	# Try with telegram_id
        	user_exists = self.session.query(User).filter(User.telegram_id == user_id).first()
        	if user_exists:
        		user_id = user_exists.id
        	else:
        		logger.warning(f"Cannot create notification: User {user_id} not found")
        		return None
        	
        try:
        	notification = Notification(
        	    user_id=user_id,
        	    title=title,
        	    message=message,
        	    type=type,
        	    data=data or {}
        	)
        	self.session.add(notification)
        	self._safe_commit()
        	return notification        	
        except Exception as e:
        	logger.error(f"Failed to create notification: {e}")
        	self.session.rollback()
        	return None
    
    def get_unread(self, user_id: int) -> List[Notification]:
        """Get unread notifications for user"""
        return self.session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).order_by(desc(Notification.created_at)).all()
    
    def mark_as_read(self, notification_id: int) -> bool:
        """Mark notification as read"""
        notification = self.session.query(Notification).filter(
            Notification.id == notification_id
        ).first()
        
        if not notification:
            return False
        
        notification.is_read = True
        self._safe_commit()
        return True
    
    def mark_all_as_read(self, user_id: int) -> int:
        """Mark all user notifications as read"""
        result = self.session.query(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).update({Notification.is_read: True})
        
        self.session.commit()
        return result
    
    def delete_old(self, days: int = 30) -> int:
        """Delete notifications older than specified days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = self.session.query(Notification).filter(
            Notification.created_at < cutoff
        ).delete()
        
        self.session.commit()
        return result


class ConnectionLogRepository(BaseRepository):
    """Repository for ConnectionLog operations"""
    
    def log_connection(self, user_id: int, status: str, **kwargs) -> ConnectionLog:
        """Create a connection log entry"""
        log = ConnectionLog(user_id=user_id, status=status, **kwargs)
        self.session.add(log)
        self._safe_commit()
        return log
    
    def get_user_connections(self, user_id: int, limit: int = 20) -> List[ConnectionLog]:
        """Get recent connection logs for user"""
        return self.session.query(ConnectionLog).filter(
            ConnectionLog.user_id == user_id
        ).order_by(
            desc(ConnectionLog.created_at)
        ).limit(limit).all()
    
    def get_failed_connections(self, hours: int = 24) -> List[ConnectionLog]:
        """Get failed connections in last X hours"""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        return self.session.query(ConnectionLog).filter(
            ConnectionLog.status == 'failed',
            ConnectionLog.created_at >= cutoff
        ).all()
    
    def get_connection_stats(self, user_id: int, days: int = 7) -> Dict[str, Any]:
        """Get connection statistics for user"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        logs = self.session.query(ConnectionLog).filter(
            ConnectionLog.user_id == user_id,
            ConnectionLog.created_at >= cutoff
        ).all()
        
        total = len(logs)
        if total == 0:
            return {'success_rate': 0, 'total': 0, 'failed': 0}
        
        failed = sum(1 for l in logs if l.status == 'failed')
        avg_latency = sum(l.latency_ms or 0 for l in logs) / total if total > 0 else 0
        
        return {
            'total': total,
            'failed': failed,
            'success_rate': ((total - failed) / total) * 100,
            'avg_latency_ms': avg_latency
        }


# Context manager for repositories
class UnitOfWork:
    """Unit of Work pattern for managing multiple repositories"""
    
    def __init__(self, session_factory):
        self.session_factory = session_factory
        self.session = None
        self.users = None
        self.trades = None
        self.settings = None
        self.notifications = None
        self.connections = None
    
    def __enter__(self):
        self.session = self.session_factory()
        self.users = UserRepository(self.session)
        self.trades = TradeRepository(self.session)
        self.settings = SettingsRepository(self.session)
        self.notifications = NotificationRepository(self.session)
        self.connections = ConnectionLogRepository(self.session)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            try:
                self.session.commit()
            except Exception as e:
                self.session.rollback()
                raise e
            finally:
                self.session.close()
        else:
            self.session.rollback()
            self.session.close()
    
    def commit(self):
        """Explicitly commit changes"""
        self.session.commit()
    
    def rollback(self):
        """Explicitly rollback changes"""
        self.session.rollback()