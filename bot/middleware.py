# fx/bot/middleware.py
import logging
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Callable, Dict, Any, Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from sqlalchemy.orm import Session

from database.repositories import UserRepository
from services.cache import CacheService, CacheKeys
from services.notification import NotificationService
from services.monitoring import MonitoringService
from config.settings import settings

logger = logging.getLogger(__name__)


class AuthMiddleware:
    """
    Authentication middleware for bot commands
    Checks if user is registered and active
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.user_repo = UserRepository(db_session)
    
    def wrap(self, handler_func: Callable) -> Callable:
        """
        Wrap a handler function with authentication check
        """
        @wraps(handler_func)
        async def wrapper(update, context):
            user_id = update.effective_user.id
            
            # Check if user exists and is active
            user = self.user_repo.get_by_telegram_id(user_id)
            
            if not user:
                await update.message.reply_text(
                    "❌ You need to register first!\n\n"
                    "Use /register to connect your MT5 account."
                )
                return
            
            if not user.is_active:
                await update.message.reply_text(
                    "❌ Your account is deactivated.\n"
                    "Please contact support for assistance."
                )
                return
            
            if user.is_banned:
                await update.message.reply_text(
                    "❌ Your account has been banned.\n"
                    "Please contact support if you believe this is an error."
                )
                return
            
            # Update last active timestamp
            user.last_active = datetime.now(timezone.utc)
            self.db.commit()
            
            # Call the original handler
            return handler_func(update, context, *args, **kwargs)
        
        return wrapper
    
    def wrap_admin(self, handler_func: Callable) -> Callable:
        """
        Wrap a handler function with admin authentication check
        """
        @wraps(handler_func)
        async def wrapper(update, context):
            user_id = update.effective_user.id
            
            # Check if user is admin
            if user_id not in settings.ADMIN_USER_IDS:
                await update.message.reply_text("❌ Unauthorized access.")
                return
            
            # Call the original handler
            return handler_func(update, context, *args, **kwargs)
        
        return wrapper


class RateLimitMiddleware:
    """
    Rate limiting middleware to prevent abuse
    Uses Redis for distributed rate limiting
    """
    
    def __init__(self, cache_service: CacheService):
        self.cache = cache_service
        self.default_limits = {
            'trade': (5, 60),  # 5 trades per minute
            'calculate': (10, 60),  # 10 calculations per minute
            'balance': (30, 60),  # 30 balance checks per minute
            'positions': (20, 60),  # 20 position checks per minute
            'settings': (20, 60),  # 20 settings changes per minute
            'default': (30, 60)  # Default 30 per minute
        }
    
    def check_rate_limit(self, user_id: int, action: str = 'default') -> tuple[bool, Optional[int]]:
        """
        Check if user has exceeded rate limit
        Returns (is_allowed, retry_after_seconds)
        """
        limit, period = self.default_limits.get(action, self.default_limits['default'])
        
        # Create rate limit key
        key = CacheKeys.rate_limit(user_id, action)
        
        # Get current count
        current = self.cache.get(key, 0)
        
        if current >= limit:
            # Get TTL for retry time
            ttl = self.cache.redis_client.ttl(key) if self.cache.redis_client else period
            return False, max(0, ttl)
        
        # Increment counter
        if current == 0:
            # First request in this period
            self.cache.set(key, 1, ttl=period)
        else:
            self.cache.increment(key)
        
        return True, None
    
    def wrap(self, action: str = 'default') -> Callable:
        """
        Wrap a handler function with rate limiting
        """
        def decorator(handler_func: Callable) -> Callable:
            @wraps(handler_func)
            async def wrapper(update, context):
                user_id = update.effective_user.id
                
                # Check rate limit
                allowed, retry_after = self.check_rate_limit(user_id, action)
                
                if not allowed:
                    await update.message.reply_text(
                        f"⏳ *Rate limit exceeded*\n\n"
                        f"Please wait {retry_after} seconds before trying again.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                
                # Call the original handler
                return handler_func(update, context, *args, **kwargs)
            
            return wrapper
        
        return decorator


class ErrorHandler:
    """
    Global error handler for the bot
    Logs errors and notifies admins
    """
    
    def __init__(self, notification_service: NotificationService, 
                 monitoring_service: MonitoringService):
        self.notification = notification_service
        self.monitoring = monitoring_service
    
    async def handle(self, update, context) -> None:
        """
        Handle errors raised in dispatcher
        """
        import traceback

        # Always log full traceback so we can see the real error
        logger.error(
            f"Exception while handling an update: {context.error}\n"
            f"{''.join(traceback.format_exception(type(context.error), context.error, context.error.__traceback__))}",
        )

        # Track in monitoring (safe - won't raise)
        try:
            self.monitoring.log_error(
                context.error,
                {
                    'update_id': update.update_id if update else None,
                    'user_id': update.effective_user.id if update and update.effective_user else None,
                    'chat_id': update.effective_chat.id if update and update.effective_chat else None
                }
            )
        except Exception as e:
            logger.warning(f"Could not log error to monitoring: {e}")

        # Notify user
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ An error occurred while processing your request.\n"
                    "Our team has been notified and will look into it."
                )
        except Exception:
            pass

        # Notify admins for critical errors
        if self._is_critical_error(context.error):
            asyncio.create_task(self._notify_admins(context.error, update))
    
    def _is_critical_error(self, error: Exception) -> bool:
        """Check if error is critical enough to notify admins"""
        critical_types = [
            'ConnectionError',
            'DatabaseError',
            'APIError',
            'AuthenticationError'
        ]
        error_type = error.__class__.__name__
        return error_type in critical_types
    
    async def _notify_admins(self, error: Exception, update: Optional[Update]):
        """Notify admins about critical errors"""
        error_text = (
            f"⚠️ *Critical Error*\n\n"
            f"Type: {error.__class__.__name__}\n"
            f"Error: {str(error)[:200]}\n"
        )
        
        if update and update.effective_user:
            error_text += f"User: {update.effective_user.id}\n"
        
        await self.notification.broadcast(
            error_text,
            user_filter={'is_admin': True}
        )


class LoggingMiddleware:
    """
    Logging middleware to track all interactions
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def wrap(self, handler_func: Callable) -> Callable:
        """
        Wrap handler function with logging
        """
        @wraps(handler_func)
        async def wrapper(update, context):
            start_time = time.time()
            user = update.effective_user
            chat = update.effective_chat
            
            # Log incoming message
            self.logger.info(
                f"Message from {user.id} (@{user.username}) in {chat.type}: "
                f"'{update.message.text if update.message else '[no text]'}'"
            )
            
            try:
                # Call handler
                result = handler_func(update, context, *args, **kwargs)
                
                # Log success
                duration = time.time() - start_time
                self.logger.info(
                    f"Handler {handler_func.__name__} completed in {duration:.3f}s"
                )
                
                return result
                
            except Exception as e:
                # Log failure
                duration = time.time() - start_time
                self.logger.error(
                    f"Handler {handler_func.__name__} failed after {duration:.3f}s: {e}"
                )
                raise
        
        return wrapper


class PerformanceMiddleware:
    """
    Performance tracking middleware
    """
    
    def __init__(self, monitoring_service: MonitoringService):
        self.monitoring = monitoring_service
        self.tracker = monitoring_service.performance_tracker
    
    def wrap(self, operation_name: str) -> Callable:
        """
        Wrap handler function with performance tracking
        """
        def decorator(handler_func: Callable) -> Callable:
            @wraps(handler_func)
            async def wrapper(update, context):
                user_id = update.effective_user.id if update.effective_user else 'unknown'
                operation_id = f"{operation_name}_{user_id}_{int(time.time())}"
                
                # Start tracking
                self.tracker.start_operation(
                    operation_id,
                    {
                        'user_id': user_id,
                        'operation': operation_name,
                        'chat_type': update.effective_chat.type if update.effective_chat else None
                    }
                )
                
                try:
                    # Call handler
                    result = handler_func(update, context, *args, **kwargs)
                    
                    # End tracking - success
                    self.tracker.end_operation(operation_id, 'success')
                    
                    return result
                    
                except Exception as e:
                    # End tracking - failure
                    self.tracker.end_operation(operation_id, 'failed')
                    raise
            
            return wrapper
        
        return decorator


class MaintenanceMiddleware:
    """
    Check if bot is in maintenance mode
    """
    
    def __init__(self, cache_service: CacheService):
        self.cache = cache_service
    
    def wrap(self, handler_func: Callable) -> Callable:
        """
        Wrap handler function with maintenance check
        """
        @wraps(handler_func)
        async def wrapper(update, context):
            # Check if maintenance mode is enabled
            maintenance_mode = self.cache.get('system:maintenance_mode', False)
            
            if maintenance_mode:
                # Check if user is admin (admins can bypass)
                user_id = update.effective_user.id
                if user_id not in settings.ADMIN_USER_IDS:
                    await update.message.reply_text(
                        "🔧 *Bot is under maintenance*\n\n"
                        "Please try again later.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
            
            # Call the original handler
            return handler_func(update, context, *args, **kwargs)
        
        return wrapper


def combine_middleware(*middleware_wrappers) -> Callable:
    """
    Combine multiple middleware wrappers
    """
    def decorator(handler_func: Callable) -> Callable:
        for wrapper in reversed(middleware_wrappers):
            handler_func = wrapper(handler_func)
        return handler_func
    
    return decorator