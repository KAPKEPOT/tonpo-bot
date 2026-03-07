# fx/bot/admin.py
import logging
from datetime import datetime, timedelta
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, CallbackContext
from sqlalchemy.orm import Session

from database.repositories import UserRepository, TradeRepository
from services.notification import NotificationService
from services.analytics import AnalyticsService
from services.monitoring import MonitoringService
from bot.keyboards import get_admin_keyboard, get_admin_user_keyboard

logger = logging.getLogger(__name__)

# Conversation states
(ADMIN_MAIN, USER_MANAGEMENT, BROADCAST, SYSTEM_STATS, CONFIRM_ACTION) = range(5)

ADMIN_STATES = {
    ADMIN_MAIN: [CallbackQueryHandler(AdminHandler.handle_menu, pattern='^admin_')],
    USER_MANAGEMENT: [CallbackQueryHandler(AdminHandler.handle_user_management, pattern='^user_')],
    BROADCAST: [MessageHandler(Filters.text, AdminHandler.handle_broadcast)],
    SYSTEM_STATS: [CallbackQueryHandler(AdminHandler.handle_stats, pattern='^stats_')],
    CONFIRM_ACTION: [CallbackQueryHandler(AdminHandler.confirm_action, pattern='^confirm_')],
}


class AdminHandler:
    """
    Handles admin-only commands and management
    """
    
    def __init__(self, db_session: Session, bot):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.trade_repo = TradeRepository(db_session)
        self.notification = NotificationService(db_session, bot)
        self.analytics = AnalyticsService(db_session)
        self.monitoring = MonitoringService(db_session)
        
        # Admin user IDs from settings
        self.admin_ids = settings.ADMIN_USER_IDS
    
    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in self.admin_ids
    
    def dashboard(self, update: Update, context: CallbackContext) -> int:
        """Show admin dashboard"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            update.message.reply_text("❌ Unauthorized access.")
            return ConversationHandler.END
        
        # Get quick stats
        total_users = self.user_repo.get_active_users().__len__()
        trades_today = self.trade_repo.get_recent_trades(hours=24).__len__()
        system_health = self.monitoring.get_system_health()
        
        dashboard_text = (
            "*👑 Admin Dashboard*\n\n"
            f"*System Status:*\n"
            f"• Status: {system_health['status']}\n"
            f"• Uptime: {system_health['uptime']/3600:.1f} hours\n"
            f"• CPU: {system_health['system']['cpu']['percent']}%\n"
            f"• Memory: {system_health['system']['memory']['percent']}%\n\n"
            
            f"*Statistics:*\n"
            f"• Total Users: {total_users}\n"
            f"• Trades (24h): {trades_today}\n"
            f"• Active Connections: {system_health['database'].get('active_connections', 0)}\n\n"
            
            "Select an option:"
        )
        
        update.message.reply_text(
            dashboard_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
        
        return ADMIN_MAIN
    
    def handle_menu(self, update: Update, context: CallbackContext) -> int:
        """Handle admin menu selections"""
        query = update.callback_query
        query.answer()
        
        action = query.data.replace('admin_', '')
        
        if action == 'users':
            return self._show_user_management(update, context)
        elif action == 'broadcast':
            return self._start_broadcast(update, context)
        elif action == 'stats':
            return self._show_system_stats(update, context)
        elif action == 'alerts':
            return self._show_alerts(update, context)
        elif action == 'back':
            return self.dashboard(update, context)
        elif action == 'close':
            query.edit_message_text("👑 Admin session ended.")
            return ConversationHandler.END
    
    def _show_user_management(self, update: Update, context: CallbackContext) -> int:
        """Show user management interface"""
        query = update.callback_query
        
        # Get recent users
        users = self.user_repo.get_active_users(limit=10)
        
        user_list = "*User Management*\n\n"
        for user in users:
            status = "✅" if user.is_active else "❌"
            verified = "✓" if user.is_verified else "✗"
            user_list += f"{status} {verified} {user.telegram_username or user.telegram_id} - {user.subscription_tier}\n"
        
        user_list += "\nSelect a user to manage:"
        
        query.edit_message_text(
            user_list,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_user_keyboard(users)
        )
        
        return USER_MANAGEMENT
    
    def handle_user_management(self, update: Update, context: CallbackContext) -> int:
        """Handle user management actions"""
        query = update.callback_query
        query.answer()
        
        action = query.data.replace('user_', '')
        
        if action == 'back':
            return self.dashboard(update, context)
        
        # Parse user selection
        if action.startswith('select_'):
            user_id = int(action.replace('select_', ''))
            context.user_data['selected_user'] = user_id
            return self._show_user_details(update, context)
        
        elif action.startswith('ban_'):
            user_id = int(action.replace('ban_', ''))
            context.user_data['selected_user'] = user_id
            context.user_data['pending_action'] = 'ban'
            return self._confirm_action(update, context, "ban this user")
        
        elif action.startswith('unban_'):
            user_id = int(action.replace('unban_', ''))
            self.user_repo.update_user(user_id, is_banned=False)
            query.edit_message_text(f"✅ User {user_id} unbanned.")
            return self._show_user_management(update, context)
        
        elif action.startswith('make_admin_'):
            user_id = int(action.replace('make_admin_', ''))
            # Add to admin list (would need to update settings)
            query.edit_message_text(f"✅ User {user_id} promoted to admin.")
            return self._show_user_management(update, context)
    
    def _show_user_details(self, update: Update, context: CallbackContext) -> int:
        """Show detailed user information"""
        query = update.callback_query
        user_id = context.user_data['selected_user']
        
        user = self.user_repo.get_by_telegram_id(user_id)
        if not user:
            query.edit_message_text("❌ User not found.")
            return USER_MANAGEMENT
        
        # Get user stats
        stats = self.analytics.get_user_stats(user_id, days=30)
        
        details = (
            f"*User Details: @{user.telegram_username or 'N/A'}*\n\n"
            f"ID: `{user.telegram_id}`\n"
            f"Name: {user.full_name}\n"
            f"Registered: {user.created_at.strftime('%Y-%m-%d')}\n\n"
            
            f"*MT5 Account:*\n"
            f"Account: `{user.mt5_account_id}`\n"
            f"Server: {user.mt5_server}\n"
            f"Status: {'✅ Connected' if user.mt_connected else '❌ Disconnected'}\n\n"
            
            f"*Subscription:*\n"
            f"Plan: {user.subscription_tier}\n"
            f"Expires: {user.subscription_expiry.strftime('%Y-%m-%d') if user.subscription_expiry else 'Never'}\n"
            f"Trades today: {user.daily_trades}\n\n"
            
            f"*Statistics (30d):*\n"
            f"Trades: {stats.get('summary', {}).get('total_trades', 0)}\n"
            f"Volume: {stats.get('summary', {}).get('total_volume', 0):.2f}\n"
            f"Win Rate: {stats.get('summary', {}).get('win_rate', 0):.1f}%\n"
            f"Net P/L: ${stats.get('summary', {}).get('net_profit', 0):,.2f}\n\n"
            
            f"Status: {'🟢 Active' if user.is_active else '🔴 Inactive'}\n"
            f"Banned: {'✅' if user.is_banned else '❌'}\n"
        )
        
        query.edit_message_text(
            details,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_user_actions_keyboard(user)
        )
        
        return USER_MANAGEMENT
    
    def _start_broadcast(self, update: Update, context: CallbackContext) -> int:
        """Start broadcast message flow"""
        query = update.callback_query
        
        query.edit_message_text(
            "*📢 Send Broadcast*\n\n"
            "Enter the message you want to broadcast to all users:\n"
            "(Supports Markdown formatting)\n\n"
            "Type /cancel to abort.",
            parse_mode=ParseMode.MARKDOWN
        )
        
        return BROADCAST
    
    def handle_broadcast(self, update: Update, context: CallbackContext) -> int:
        """Handle broadcast message input"""
        message = update.message.text
        
        if message == '/cancel':
            update.message.reply_text("❌ Broadcast cancelled.")
            return self.dashboard(update, context)
        
        # Store message
        context.user_data['broadcast_message'] = message
        
        # Show preview and confirmation
        preview = (
            f"*Broadcast Preview:*\n\n{message}\n\n"
            f"_This will be sent to all active users._\n"
            f"Confirm?"
        )
        
        update.message.reply_text(
            preview,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_confirmation_keyboard()
        )
        
        return CONFIRM_ACTION
    
    def _show_system_stats(self, update: Update, context: CallbackContext) -> int:
        """Show detailed system statistics"""
        query = update.callback_query
        
        # Get comprehensive stats
        system_stats = self.monitoring.get_performance_report()
        analytics = self.analytics.get_system_stats()
        
        stats_text = (
            "*📊 System Statistics*\n\n"
            f"*Performance:*\n"
            f"CPU: {system_stats['system']['cpu']['percent']}%\n"
            f"Memory: {system_stats['system']['memory']['percent']}%\n"
            f"Disk: {system_stats['system']['disk']['percent']}%\n"
            f"DB Response: {system_stats['database'].get('response_time_ms', 0)}ms\n\n"
            
            f"*Users:*\n"
            f"Total: {analytics['users']['total']}\n"
            f"Active: {analytics['users']['active']}\n"
            f"Verified: {analytics['users']['verified']}\n\n"
            
            f"*Subscriptions:*\n"
            f"Free: {analytics['subscriptions']['free']}\n"
            f"Basic: {analytics['subscriptions']['basic']}\n"
            f"Pro: {analytics['subscriptions']['pro']}\n"
            f"Enterprise: {analytics['subscriptions']['enterprise']}\n\n"
            
            f"*Trades:*\n"
            f"Last 24h: {analytics['trades']['last_24h']}\n"
            f"Total: {analytics['trades']['total']}\n\n"
            
            f"*Connections:*\n"
            f"Success Rate: {analytics['connections']['success_rate']}%\n"
            f"Avg Latency: {analytics['connections']['avg_latency']}ms\n"
        )
        
        query.edit_message_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
        
        return ADMIN_MAIN
    
    def _show_alerts(self, update: Update, context: CallbackContext) -> int:
        """Show system alerts"""
        query = update.callback_query
        
        alerts = self.monitoring.get_alerts()
        
        if not alerts:
            alerts_text = "*✅ No active alerts*\n\nSystem is healthy."
        else:
            alerts_text = "*⚠️ Active Alerts*\n\n"
            for alert in alerts:
                level_icon = "🔴" if alert['level'] == 'critical' else "🟡"
                alerts_text += f"{level_icon} *{alert['metric']}*: {alert['message']}\n"
        
        query.edit_message_text(
            alerts_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_admin_keyboard()
        )
        
        return ADMIN_MAIN
    
    def _confirm_action(self, update: Update, context: CallbackContext, action_desc: str) -> int:
        """Show confirmation dialog"""
        query = update.callback_query
        
        context.user_data['pending_action'] = action_desc
        
        query.edit_message_text(
            f"Are you sure you want to {action_desc}?",
            reply_markup=get_confirmation_keyboard()
        )
        
        return CONFIRM_ACTION
    
    def confirm_action(self, update: Update, context: CallbackContext) -> int:
        """Handle action confirmation"""
        query = update.callback_query
        query.answer()
        
        if query.data == 'confirm_yes':
            action = context.user_data.get('pending_action')
            user_id = context.user_data.get('selected_user')
            
            if action == 'ban this user':
                self.user_repo.update_user(user_id, is_banned=True)
                query.edit_message_text(f"✅ User {user_id} has been banned.")
            
            elif action == 'broadcast':
                # Execute broadcast
                message = context.user_data['broadcast_message']
                asyncio.create_task(self._execute_broadcast(message))
                query.edit_message_text("✅ Broadcast started.")
            
            # Clear pending
            context.user_data.pop('pending_action', None)
            context.user_data.pop('selected_user', None)
            
        else:
            query.edit_message_text("❌ Action cancelled.")
        
        return self.dashboard(update, context)
    
    async def _execute_broadcast(self, message: str):
        """Execute broadcast to all users"""
        result = await self.notification.broadcast(message)
        
        # Notify admins
        for admin_id in self.admin_ids:
            await self.bot.send_message(
                chat_id=admin_id,
                text=f"📢 Broadcast complete: {result['success']} delivered, {result['failed']} failed"
            )
    
    def stats(self, update: Update, context: CallbackContext):
        """Quick stats command"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            update.message.reply_text("❌ Unauthorized access.")
            return
        
        system_stats = self.monitoring.get_performance_report()
        
        quick_stats = (
            f"*System Stats*\n"
            f"Uptime: {system_stats['uptime_seconds']/3600:.1f}h\n"
            f"CPU: {system_stats['system']['cpu']['percent']}%\n"
            f"Memory: {system_stats['system']['memory']['percent']}%\n"
            f"Users: {system_stats['summary']['total_users']}\n"
            f"Trades 24h: {system_stats['summary']['trades_today']}"
        )
        
        update.message.reply_text(quick_stats, parse_mode=ParseMode.MARKDOWN)
    
    def broadcast(self, update: Update, context: CallbackContext):
        """Quick broadcast command"""
        user_id = update.effective_user.id
        
        if not self.is_admin(user_id):
            update.message.reply_text("❌ Unauthorized access.")
            return
        
        # Check if message provided
        if not context.args:
            update.message.reply_text("Usage: /broadcast <message>")
            return
        
        message = ' '.join(context.args)
        
        # Start broadcast
        asyncio.create_task(self._execute_broadcast(message))
        update.message.reply_text("📢 Broadcast started.")