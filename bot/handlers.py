# fx/bot/handlers.py
import logging
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from sqlalchemy.orm import Session

from database.repositories import UserRepository, TradeRepository
from services.notification import NotificationService
from services.subscription import SubscriptionService
from utils.formatters import format_balance, format_positions, format_trade_history

logger = logging.getLogger(__name__)


class CommandHandlers:
    """
    Basic command handlers (start, help, balance, etc.)
    """
    
    def __init__(self, db_session: Session, bot):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.trade_repo = TradeRepository(db_session)
        self.notification = NotificationService(db_session, bot)
        self.sub_service = SubscriptionService(db_session)
    
    async def start(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        user = update.effective_user
        db_user = self.user_repo.get_by_telegram_id(user.id)
        is_admin = user.id in settings.ADMIN_USER_IDS
        
        if db_user:
            message = (
                f"👋 Welcome back, {user.first_name}!\n\n"
                f"Your MT5 account ({db_user.mt5_account_id}) is connected.\n"
                f"Plan: *{db_user.subscription_tier.upper()}*\n\n"
                "What would you like to do?\n"
                "• /trade - Place a trade\n"
                "• /balance - Check balance\n"
                "• /positions - View open positions\n"
                "• /settings - Configure settings"
            )
            
            if is_admin:
            	message += (
            	    "\n\n*👑 Admin Commands:*\n"
            	    "• /admin - Admin dashboard\n"
            	    "• /stats - Quick system stats\n"
            	    "• /broadcast - Send message to all users"
            	)
            	
        else:
            message = (
                "🚀 *Welcome to FX Signal Copier!*\n\n"
                "I help you execute forex trades directly from Telegram "
                "to your MetaTrader 5 account.\n\n"
                "To get started, use /register to connect your MT5 account.\n"
                "Use /help to see all commands."
            )
            
            if is_admin:
            	message += (
            	    "\n\n*👑 You have admin access.*\n"
            	    "Use /admin for the dashboard (no registration needed)."
            	)
        
        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    async def help(self, update: Update, context: CallbackContext):
        """Handle /help command"""
        help_text = (
            "*📚 FX Signal Copier Commands*\n\n"
            "*Getting Started:*\n"
            "/register - Connect your MT5 account\n"
            "/settings - Configure your preferences\n\n"
            
            "*Trading:*\n"
            "/trade - Place a new trade\n"
            "/calculate - Calculate risk without trading\n"
            "/balance - Check account balance\n"
            "/positions - View open positions\n"
            "/history - View trade history\n\n"
            
            "*Account:*\n"
            "/profile - View your profile\n"
            "/upgrade - Upgrade subscription\n"
            "/referral - Get referral link\n\n"
            
            "*Support:*\n"
            "/help - Show this message\n"
            "/about - About the bot\n"
            "/contact - Contact support\n\n"
            
            "*Trade Format:*\n"
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
        )
        
        # Add admin commands if user is admin
        if update.effective_user.id in settings.ADMIN_USER_IDS:
            help_text += (
                "\n*👑 Admin Commands:*\n"
                "/admin - Admin dashboard\n"
                "/stats - Quick system stats\n"
                "/broadcast <message> - Broadcast to all users\n"
            )
        
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        
    async def about(self, update: Update, context: CallbackContext):
        """Handle /about command"""
        about_text = (
            "*🤖 About FX Signal Copier*\n\n"
            "Version: 2.0.0\n"
            "Author: Your Name\n"
            "License: Proprietary\n\n"
            
            "*Features:*\n"
            "• Automated trade execution\n"
            "• Smart risk management\n"
            "• Multiple take profits\n"
            "• Real-time notifications\n"
            "• Advanced analytics\n\n"
            
            "*Supported Brokers:*\n"
            "Any MetaTrader 5 broker\n\n"
            
            "*Support:*\n"
            "Join our community @fx_signal_copier"
        )
        
        await update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)
    
    async def balance(self, update: Update, context: CallbackContext):
        """Handle /balance command"""
        user_id = update.effective_user.id
        
        # This will be handled by the trading handler with MT5 connection
        context.user_data['action'] = 'balance'
        return await self._forward_to_trading(update, context)
    
    async def positions(self, update: Update, context: CallbackContext):
        """Handle /positions command"""
        user_id = update.effective_user.id
        
        context.user_data['action'] = 'positions'
        return await self._forward_to_trading(update, context)
    
    async def history(self, update: Update, context: CallbackContext):
        """Handle /history command"""
        user_id = update.effective_user.id
        db_user = self.user_repo.get_by_telegram_id(user_id)
        
        if not db_user:
            await update.message.reply_text("Please register first using /register")
            return
        
        trades = self.trade_repo.get_user_trades(db_user.id, limit=20)
        
        if not trades:
            await update.message.reply_text("No trade history found.")
            return
        
        history_text = format_trade_history(trades)
        await update.message.reply_text(history_text, parse_mode=ParseMode.HTML)
    
    async def profile(self, update: Update, context: CallbackContext):
        """Handle /profile command"""
        user_id = update.effective_user.id
        db_user = self.user_repo.get_by_telegram_id(user_id)
        
        if not db_user:
            await update.message.reply_text("Please register first using /register")
            return
        
        # Get subscription info
        plan = self.sub_service.get_user_plan(user_id)
        usage = self.sub_service.get_usage_stats(user_id)
        
        profile_text = (
            f"*👤 User Profile*\n\n"
            f"Telegram ID: `{db_user.telegram_id}`\n"
            f"Username: @{db_user.telegram_username or 'None'}\n"
            f"Member since: {db_user.created_at.strftime('%Y-%m-%d')}\n\n"
            
            f"*MT5 Account:*\n"
            f"Account: `{db_user.mt5_account_id}`\n"
            f"Server: {db_user.mt5_server}\n"
            f"Status: {'✅ Connected' if db_user.mt_connected else '❌ Disconnected'}\n\n"
            
            f"*Subscription:*\n"
            f"Plan: *{db_user.subscription_tier.upper()}*\n"
            f"Trades today: {usage.get('trades_today', 0)}/{plan.max_trades_per_day}\n"
            f"Expires: {db_user.subscription_expiry.strftime('%Y-%m-%d') if db_user.subscription_expiry else 'Never'}\n\n"
            
            f"*Statistics:*\n"
            f"Total Trades: {db_user.total_trades}\n"
            f"Total Volume: {db_user.total_volume:.2f}\n"
            f"Win Rate: {db_user.win_rate:.1f}%\n"
        )
        
        await update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN)
    
    async def upgrade(self, update: Update, context: CallbackContext):
        """Handle /upgrade command — shows plans dynamically from database"""
        from bot.keyboards import get_plans_keyboard
        
        # Get user's current plan
        user_id = update.effective_user.id
        user = self.user_repo.get_by_telegram_id(user_id)
        current_tier = user.subscription_tier if user else 'free'
        
        # Fetch all plans from database
        plans = self.sub_service.get_all_plans()
        
        if not plans:
            await update.message.reply_text(
                "❌ No subscription plans available. Please contact support."
            )
            return
        
        # Sort plans by price
        plans.sort(key=lambda p: float(p.price_monthly))
        
        # Build dynamic plan display
        text = "*📊 Subscription Plans*\n\n"
        
        for plan in plans:
            # Current plan indicator
            current = " ← *Your Plan*" if plan.tier == current_tier else ""
            
            # Price display
            if plan.is_free:
                price_str = "Free"
            else:
                price_str = f"${plan.price_monthly}/month · ${plan.price_yearly}/year"
            
            text += f"*{plan.name} Plan*{current}\n"
            text += f"💰 {price_str}\n"
            text += f"• {plan.max_trades_per_day} trades per day\n"
            text += f"• {plan.max_position_size} max position size\n"
            
            if plan.supports_multiple_tps:
                text += "• ✅ Multiple TPs\n"
            if plan.supports_auto_trading:
                text += "• ✅ Auto-trading\n"
            if plan.supports_api:
                text += "• ✅ API access\n"
            if plan.max_connections > 1:
                text += f"• {plan.max_connections} MT5 accounts\n"
            if plan.support_priority == 'high':
                text += "• ⚡ Priority support\n"
            
            text += "\n"
        
        # Add expiry info if user has paid plan
        if user and user.subscription_expiry and current_tier != 'free':
            from datetime import datetime
            days_left = (user.subscription_expiry - datetime.utcnow()).days
            if days_left > 0:
                text += f"_Your {current_tier.title()} plan expires in {days_left} days_\n\n"
            else:
                text += "_⚠️ Your plan has expired_\n\n"
        
        text += "Select a plan to see details:"
        
        await update.message.reply_text(
            text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_plans_keyboard()
        )
    
    async def unknown(self, update: Update, context: CallbackContext):
        """Handle unknown commands"""
        await update.message.reply_text(
            "❌ Unknown command. Use /help to see available commands."
        )
    
    async def _forward_to_trading(self, update: Update, context: CallbackContext):
        """Forward to trading handler for MT5 operations"""
        from bot.trading import TradingHandler
        
        handler = TradingHandler(self.db, self.bot)
        return await handler.handle_action(update, context)