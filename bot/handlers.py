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
    
    def start(self, update: Update, context: CallbackContext):
        """Handle /start command"""
        user = update.effective_user
        db_user = self.user_repo.get_by_telegram_id(user.id)
        
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
        else:
            message = (
                "🚀 *Welcome to FX Signal Copier!*\n\n"
                "I help you execute forex trades directly from Telegram "
                "to your MetaTrader 5 account.\n\n"
                "To get started, use /register to connect your MT5 account.\n"
                "Use /help to see all commands."
            )
        
        update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
    
    def help(self, update: Update, context: CallbackContext):
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
        
        update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
    
    def about(self, update: Update, context: CallbackContext):
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
        
        update.message.reply_text(about_text, parse_mode=ParseMode.MARKDOWN)
    
    def balance(self, update: Update, context: CallbackContext):
        """Handle /balance command"""
        user_id = update.effective_user.id
        
        # This will be handled by the trading handler with MT5 connection
        context.user_data['action'] = 'balance'
        return self._forward_to_trading(update, context)
    
    def positions(self, update: Update, context: CallbackContext):
        """Handle /positions command"""
        user_id = update.effective_user.id
        
        context.user_data['action'] = 'positions'
        return self._forward_to_trading(update, context)
    
    def history(self, update: Update, context: CallbackContext):
        """Handle /history command"""
        user_id = update.effective_user.id
        db_user = self.user_repo.get_by_telegram_id(user_id)
        
        if not db_user:
            update.message.reply_text("Please register first using /register")
            return
        
        trades = self.trade_repo.get_user_trades(db_user.id, limit=20)
        
        if not trades:
            update.message.reply_text("No trade history found.")
            return
        
        history_text = format_trade_history(trades)
        update.message.reply_text(history_text, parse_mode=ParseMode.HTML)
    
    def profile(self, update: Update, context: CallbackContext):
        """Handle /profile command"""
        user_id = update.effective_user.id
        db_user = self.user_repo.get_by_telegram_id(user_id)
        
        if not db_user:
            update.message.reply_text("Please register first using /register")
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
        
        update.message.reply_text(profile_text, parse_mode=ParseMode.MARKDOWN)
    
    def upgrade(self, update: Update, context: CallbackContext):
        """Handle /upgrade command"""
        from bot.keyboards import get_plans_keyboard
        
        plans_text = (
            "*📊 Subscription Plans*\n\n"
            "Choose a plan that fits your trading style:\n\n"
            
            "*Free Plan*\n"
            "• 10 trades per day\n"
            "• 1.0 max position size\n"
            "• Basic features\n"
            "• Price: $0\n\n"
            
            "*Basic Plan*\n"
            "• 50 trades per day\n"
            "• 5.0 max position size\n"
            "• Multiple TPs\n"
            "• Priority support\n"
            "• Price: $9.99/month\n\n"
            
            "*Pro Plan*\n"
            "• 200 trades per day\n"
            "• 10.0 max position size\n"
            "• Auto-trading\n"
            "• API access\n"
            "• Price: $29.99/month\n\n"
            
            "*Enterprise Plan*\n"
            "• Unlimited trades\n"
            "• 50.0 max position size\n"
            "• Multiple accounts\n"
            "• Custom features\n"
            "• Price: $99.99/month"
        )
        
        update.message.reply_text(
            plans_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_plans_keyboard()
        )
    
    def unknown(self, update: Update, context: CallbackContext):
        """Handle unknown commands"""
        update.message.reply_text(
            "❌ Unknown command. Use /help to see available commands."
        )
    
    def _forward_to_trading(self, update: Update, context: CallbackContext):
        """Forward to trading handler for MT5 operations"""
        from bot.trading import TradingHandler
        
        handler = TradingHandler(self.db, self.bot)
        return handler.handle_action(update, context)