# fx/bot/callbacks.py
import logging
from typing import Dict, Any, Optional
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from sqlalchemy.orm import Session

from database.repositories import UserRepository, TradeRepository
from services.notification import NotificationService
from services.subscription import SubscriptionService
from bot.keyboards import (
    get_settings_keyboard, get_plans_keyboard,
    get_confirmation_keyboard, get_pagination_keyboard
)

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """
    Handles all callback queries from inline keyboards
    """
    
    def __init__(self, db_session: Session, bot):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.trade_repo = TradeRepository(db_session)
        self.notification = NotificationService(db_session, bot)
        self.sub_service = SubscriptionService(db_session)
        
        # Register handlers
        self.handlers = {
            'plan': self.handle_plan,
            'notification': self.handle_notification,
            'trade': self.handle_trade_action,
            'position': self.handle_position,
            'pagination': self.handle_pagination,
            'confirm': self.handle_confirmation,
            'help': self.handle_help,
        }
    
    async def handle(self, update: Update, context: CallbackContext) -> None:
        """
        Main callback handler - routes to appropriate sub-handler
        """
        query = update.callback_query
        await query.answer()
        
        data = query.data
        if not data:
            return
        
        # Parse callback data format: "handler:action:data"
        parts = data.split(':')
        handler_name = parts[0]
        
        # Find and execute handler
        handler = self.handlers.get(handler_name)
        if handler:
            await handler(update, context, parts[1:])
        else:
            logger.warning(f"No handler for callback: {data}")
            await query.edit_message_text("Unknown action.")
    
    async def handle_plan(self, update: Update, context: CallbackContext, args: list):
        """Handle subscription plan callbacks"""
        query = update.callback_query
        action = args[0] if args else 'list'
        
        if action == 'list':
            # Show plan list
            plans = self.sub_service.get_all_plans()
            
            text = "*📊 Subscription Plans*\n\n"
            for plan in plans:
                text += (
                    f"*{plan.name}*\n"
                    f"• ${plan.price_monthly}/month\n"
                    f"• {plan.max_trades_per_day} trades/day\n"
                    f"• {plan.max_position_size} max lots\n"
                    f"• Multiple TPs: {'✅' if plan.supports_multiple_tps else '❌'}\n"
                    f"• Auto-trading: {'✅' if plan.supports_auto_trading else '❌'}\n\n"
                )
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_plans_keyboard()
            )
        
        elif action == 'select':
            # Show specific plan details
            plan_tier = args[1]
            plan = self.sub_service.get_plan(plan_tier)
            
            if not plan:
                await query.edit_message_text("❌ Plan not found.")
                return
            
            user_id = update.effective_user.id
            current_plan = self.sub_service.get_user_plan(user_id)
            
            text = (
                f"*{plan.name} Plan*\n\n"
                f"Price: ${plan.price_monthly}/month or ${plan.price_yearly}/year\n\n"
                f"*Features:*\n"
                f"• {plan.max_trades_per_day} trades per day\n"
                f"• {plan.max_position_size} max position size\n"
                f"• Multiple TPs: {'✅' if plan.supports_multiple_tps else '❌'}\n"
                f"• Auto-trading: {'✅' if plan.supports_auto_trading else '❌'}\n"
                f"• API access: {'✅' if plan.supports_api else '❌'}\n"
                f"• Support priority: {plan.support_priority}\n\n"
            )
            
            if plan.features:
                text += "*Additional Features:*\n"
                for feature in plan.features:
                    text += f"• {feature}\n"
            
            if current_plan.tier == plan_tier:
                text += "\n✅ *This is your current plan*"
                keyboard = None
            else:
                from bot.keyboards import get_upgrade_keyboard
                keyboard = get_upgrade_keyboard(plan_tier)
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=keyboard
            )
        
        elif action == 'upgrade':
            # Process upgrade
            plan_tier = args[1]
            user_id = update.effective_user.id
            
            # Check if already on this plan
            current = self.sub_service.get_user_plan(user_id)
            if current.tier == plan_tier:
                await query.edit_message_text("✅ You are already on this plan.")
                return
            
            # Show payment options
            text = (
                f"*Upgrade to {plan_tier}*\n\n"
                "Choose payment method:\n\n"
                "• 💳 Credit Card\n"
                "• ₿ Bitcoin\n"
                "• 💵 PayPal\n\n"
                "Select an option below:"
            )
            
            from bot.keyboards import get_payment_keyboard
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_payment_keyboard(plan_tier)
            )
    
    async def handle_notification(self, update: Update, context: CallbackContext, args: list):
        """Handle notification callbacks"""
        query = update.callback_query
        action = args[0]
        
        user_id = update.effective_user.id
        settings = self.user_repo.get_by_telegram_id(user_id).settings
        
        if action == 'mark_read':
            # Mark all as read
            from database.repositories import NotificationRepository
            repo = NotificationRepository(self.db)
            count = repo.mark_all_as_read(user_id)
            
            await query.edit_message_text(f"✅ Marked {count} notifications as read.")
        
        elif action == 'view':
            # View specific notification
            notif_id = int(args[1])
            from database.models import Notification
            
            notif = self.db.query(Notification).filter(
                Notification.id == notif_id,
                Notification.user_id == user_id
            ).first()
            
            if notif:
                # Mark as read
                notif.is_read = True
                self.db.commit()
                
                text = (
                    f"*{notif.title}*\n\n"
                    f"{notif.message}\n\n"
                    f"_{notif.created_at.strftime('%Y-%m-%d %H:%M UTC')}_"
                )
                
                await query.edit_message_text(
                    text,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await query.edit_message_text("❌ Notification not found.")
        
        elif action == 'clear':
            # Clear all notifications
            count = self.db.query(Notification).filter(
                Notification.user_id == user_id
            ).delete()
            self.db.commit()
            
            await query.edit_message_text(f"✅ Cleared {count} notifications.")
    
    async def handle_trade_action(self, update: Update, context: CallbackContext, args: list):
        """Handle trade-related callbacks"""
        query = update.callback_query
        action = args[0]
        
        if action == 'close':
            # Close a position
            position_id = args[1]
            
            from services.trade_executor import TradeExecutor
            executor = TradeExecutor(self.db, self.bot)
            
            result = await executor.close_trade(update.effective_user.id, position_id)
            
            if result['success']:
                await query.edit_message_text(f"✅ Position {position_id} closed.")
            else:
                await query.edit_message_text(f"❌ Failed to close: {result['error']}")
        
        elif action == 'modify':
            # Modify position
            position_id = args[1]
            
            # Store in context for modification flow
            context.user_data['modify_position'] = position_id
            
            await query.edit_message_text(
                "Enter new Stop Loss and Take Profit:\n"
                "Format: `SL PRICE TP PRICE`\n"
                "Example: `1.25000 1.26000`"
            )
        
        elif action == 'history':
            # View trade history
            page = int(args[1]) if len(args) > 1 else 1
            user_id = update.effective_user.id
            db_user = self.user_repo.get_by_telegram_id(user_id)
            
            trades = self.trade_repo.get_user_trades(db_user.id, limit=10, offset=(page-1)*10)
            total = self.trade_repo.get_user_trades(db_user.id, limit=10000).__len__()
            total_pages = (total + 9) // 10
            
            if not trades:
                await query.edit_message_text("No trade history found.")
                return
            
            text = "*📊 Trade History*\n\n"
            for trade in trades[:10]:
                profit_icon = "✅" if trade.profit_loss and trade.profit_loss > 0 else "❌" if trade.profit_loss and trade.profit_loss < 0 else "⏳"
                text += (
                    f"{profit_icon} {trade.order_type} {trade.symbol}\n"
                    f"   Size: {trade.position_size} | Status: {trade.status}\n"
                    f"   {trade.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"
                )
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_pagination_keyboard(page, total_pages, 'trade_history')
            )
    
    async def handle_position(self, update: Update, context: CallbackContext, args: list):
        """Handle position-related callbacks"""
        query = update.callback_query
        action = args[0]
        
        if action == 'view':
            # View position details
            position_id = args[1]
            
            from services.mt5_manager import MT5ConnectionManager
            mt5 = MT5ConnectionManager(self.db)
            
            try:
                connection = await mt5.get_connection(update.effective_user.id)
                positions = await connection.get_positions()
                
                position = next((p for p in positions if p['id'] == position_id), None)
                
                if position:
                    text = (
                        f"*Position Details*\n\n"
                        f"ID: `{position['id']}`\n"
                        f"Symbol: {position['symbol']}\n"
                        f"Type: {position['type']}\n"
                        f"Volume: {position['volume']}\n"
                        f"Open Price: {position['openPrice']}\n"
                        f"Current Price: {position['currentPrice']}\n"
                        f"SL: {position['stopLoss']}\n"
                        f"TP: {position['takeProfit']}\n"
                        f"Profit: {position['profit']}\n"
                        f"Swap: {position['swap']}\n"
                    )
                    
                    await query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
                else:
                    await query.edit_message_text("❌ Position not found.")
                    
            except Exception as e:
                await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
        
        elif action == 'close_all':
            # Close all positions
            from bot.keyboards import get_confirmation_keyboard
            
            await query.edit_message_text(
                "Are you sure you want to close ALL positions?",
                reply_markup=get_confirmation_keyboard('close_all_positions')
            )
    
    async def handle_pagination(self, update: Update, context: CallbackContext, args: list):
        """Handle pagination callbacks"""
        query = update.callback_query
        pagination_type = args[0]
        page = int(args[1])
        
        if pagination_type == 'trade_history':
            # Forward to trade history with new page
            await self.handle_trade_action(update, context, ['history', str(page)])
        
        elif pagination_type == 'notifications':
            # Show notifications page
            user_id = update.effective_user.id
            from database.repositories import NotificationRepository
            
            repo = NotificationRepository(self.db)
            notifications = repo.get_unread(user_id)
            
            # Paginate
            start = (page - 1) * 5
            end = start + 5
            page_notifs = notifications[start:end]
            total_pages = (len(notifications) + 4) // 5
            
            if not page_notifs:
                await query.edit_message_text("No notifications.")
                return
            
            text = "*🔔 Notifications*\n\n"
            for notif in page_notifs:
                icon = "🆕" if not notif.is_read else "📌"
                text += f"{icon} {notif.title}\n"
                text += f"   {notif.created_at.strftime('%H:%M')} - {notif.message[:50]}...\n\n"
            
            await query.edit_message_text(
                text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_pagination_keyboard(page, total_pages, 'notifications')
            )
    
    async def handle_confirmation(self, update: Update, context: CallbackContext, args: list):
        """Handle confirmation callbacks"""
        query = update.callback_query
        action = args[0]
        confirmed = args[1] == 'yes'
        
        if not confirmed:
            await query.edit_message_text("❌ Action cancelled.")
            return
        
        # Process confirmed actions
        if action == 'close_all_positions':
            # Close all positions
            from services.trade_executor import TradeExecutor
            executor = TradeExecutor(self.db, self.bot)
            
            # Get all positions
            from services.mt5_manager import MT5ConnectionManager
            mt5 = MT5ConnectionManager(self.db)
            
            try:
                connection = await mt5.get_connection(update.effective_user.id)
                positions = await connection.get_positions()
                
                closed = 0
                failed = 0
                
                for position in positions:
                    success = await executor.close_trade(
                        update.effective_user.id,
                        position['id']
                    )
                    if success:
                        closed += 1
                    else:
                        failed += 1
                
                await query.edit_message_text(
                    f"✅ Closed {closed} positions. Failed: {failed}"
                )
                
            except Exception as e:
                await query.edit_message_text(f"❌ Error: {str(e)[:100]}")
        
        elif action == 'delete_account':
            # Delete user account
            user_id = update.effective_user.id
            self.user_repo.delete_user(user_id)
            
            await query.edit_message_text(
                "✅ Your account has been deleted.\n"
                "Sorry to see you go! Use /register if you change your mind."
            )
    
    async def handle_help(self, update: Update, context: CallbackContext, args: list):
        """Handle help section callbacks"""
        query = update.callback_query
        section = args[0] if args else 'main'
        
        help_texts = {
            'main': (
                "*📚 Help Center*\n\n"
                "Select a topic below:"
            ),
            'trading': (
                "*📈 Trading Help*\n\n"
                "To place a trade, use:\n"
                "`/trade`\n\n"
                "Format:\n"
                "```\n"
                "BUY/SELL [LIMIT/STOP] SYMBOL\n"
                "Entry PRICE or NOW\n"
                "SL PRICE\n"
                "TP1 PRICE\n"
                "TP2 PRICE (optional)\n"
                "```\n\n"
                "Example:\n"
                "```\n"
                "BUY GBPUSD\n"
                "Entry NOW\n"
                "SL 1.25000\n"
                "TP 1.26000\n"
                "```"
            ),
            'risk': (
                "*⚖️ Risk Management*\n\n"
                "The bot calculates position size based on:\n"
                "• Account balance\n"
                "• Stop loss in pips\n"
                "• Your risk percentage\n\n"
                "Formula: `(Balance × Risk%) ÷ (SL pips × $10)`\n\n"
                "Set your risk in /settings"
            ),
            'subscription': (
                "*💎 Subscription Plans*\n\n"
                "• Free: 10 trades/day\n"
                "• Basic: 50 trades/day, multiple TPs\n"
                "• Pro: 200 trades/day, auto-trading\n"
                "• Enterprise: Unlimited\n\n"
                "Use /upgrade to see plans"
            ),
            'api': (
                "*🔌 API Access*\n\n"
                "Generate an API key in /settings to access the bot programmatically.\n\n"
                "Use the key in headers:\n"
                "`X-API-Key: your-key-here`"
            )
        }
        
        text = help_texts.get(section, help_texts['main'])
        
        from bot.keyboards import get_help_keyboard
        await query.edit_message_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_help_keyboard(section)
        )