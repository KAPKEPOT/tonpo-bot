# fx/bot/settings.py
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, CallbackContext, CallbackQueryHandler, MessageHandler, filters
from sqlalchemy.orm import Session

from database.repositories import UserRepository, SettingsRepository
from services.auth import AuthService
from bot.keyboards import (
    get_settings_keyboard, get_risk_settings_keyboard,
    get_notification_settings_keyboard, get_symbol_settings_keyboard
)

logger = logging.getLogger(__name__)

# Conversation states
(MAIN_MENU, RISK_SETTINGS, NOTIFICATION_SETTINGS, SYMBOL_SETTINGS,
 CONNECTION_SETTINGS, API_SETTINGS, CONFIRM_UPDATE) = range(7)

class SettingsHandler:
    """
    Handles user settings management
    """
    
    def __init__(self, db_session: Session, bot):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.settings_repo = SettingsRepository(db_session)
        self.auth_service = AuthService(db_session)
    
    async def start(self, update: Update, context: CallbackContext) -> int:
        """Start settings menu"""
        user_id = update.effective_user.id
        db_user = self.user_repo.get_by_telegram_id(user_id)
        
        if not db_user:
            await update.message.reply_text(
                "❌ Please register first using /register"
            )
            return ConversationHandler.END
        
        # Store user ID in context
        context.user_data['settings_user_id'] = user_id
        
        # Show main menu
        settings_text = self._format_settings_summary(db_user)
        
        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_settings_keyboard()
        )
        
        return MAIN_MENU
    
    async def handle_menu(self, update: Update, context: CallbackContext) -> int:
        """Handle main menu selections"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('settings_', '')
        
        if action == 'risk':
            return self._show_risk_settings(update, context)
        elif action == 'notifications':
            return self._show_notification_settings(update, context)
        elif action == 'symbols':
            return self._show_symbol_settings(update, context)
        elif action == 'connection':
            return self._show_connection_settings(update, context)
        elif action == 'api':
            return self._show_api_settings(update, context)
        elif action == 'back':
            await query.edit_message_text(
                self._format_settings_summary(
                    self.user_repo.get_by_telegram_id(context.user_data['settings_user_id'])
                ),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=get_settings_keyboard()
            )
            return MAIN_MENU
        elif action == 'close':
            await query.edit_message_text("⚙️ Settings closed.")
            return ConversationHandler.END
    
    async def _show_risk_settings(self, update: Update, context: CallbackContext) -> int:
        """Show risk settings menu"""
        query = update.callback_query
        user_id = context.user_data['settings_user_id']
        user = self.user_repo.get_by_telegram_id(user_id)
        
        risk_text = (
            "*⚖️ Risk Settings*\n\n"
            f"Current risk factor: *{user.default_risk_factor*100:.1f}%*\n"
            f"Max position size: *{user.max_position_size}*\n\n"
            "Choose an option to modify:"
        )
        
        await query.edit_message_text(
            risk_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_risk_settings_keyboard(user)
        )
        
        return RISK_SETTINGS
    
    async def handle_risk(self, update: Update, context: CallbackContext) -> int:
        """Handle risk settings updates"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('risk_', '')
        user_id = context.user_data['settings_user_id']
        
        if action == 'default':
            await query.edit_message_text(
                "Enter new default risk percentage (e.g., 1.5 for 1.5%):"
            )
            context.user_data['awaiting'] = 'risk_factor'
            return CONFIRM_UPDATE
        
        elif action == 'max_size':
            await query.edit_message_text(
                "Enter new maximum position size in lots:"
            )
            context.user_data['awaiting'] = 'max_size'
            return CONFIRM_UPDATE
        
        elif action == 'back':
            return self._show_risk_settings(update, context)
    
    async def _show_notification_settings(self, update: Update, context: CallbackContext) -> int:
        """Show notification settings menu"""
        query = update.callback_query
        user_id = context.user_data['settings_user_id']
        settings = self.settings_repo.get_by_telegram_id(user_id)
        
        notif_text = (
            "*🔔 Notification Settings*\n\n"
            f"Trade notifications: {'✅' if settings.notify_on_trade else '❌'}\n"
            f"Error notifications: {'✅' if settings.notify_on_error else '❌'}\n"
            f"Daily reports: {'✅' if settings.notify_daily_report else '❌'}\n"
            f"Report time: {settings.notification_hour}:00 UTC\n\n"
            "Toggle settings below:"
        )
        
        await query.edit_message_text(
            notif_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_notification_settings_keyboard(settings)
        )
        
        return NOTIFICATION_SETTINGS
    
    async def handle_notifications(self, update: Update, context: CallbackContext) -> int:
        """Handle notification settings updates"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('notify_', '')
        user_id = context.user_data['settings_user_id']
        settings = self.settings_repo.get_by_telegram_id(user_id)
        
        if action == 'trade':
            settings.notify_on_trade = not settings.notify_on_trade
        elif action == 'error':
            settings.notify_on_error = not settings.notify_on_error
        elif action == 'daily':
            settings.notify_daily_report = not settings.notify_daily_report
        elif action == 'hour':
            await query.edit_message_text(
                "Enter notification hour (0-23 UTC):"
            )
            context.user_data['awaiting'] = 'notify_hour'
            return CONFIRM_UPDATE
        elif action == 'back':
            return self._show_notification_settings(update, context)
        
        # Save and refresh
        self.db.commit()
        return self._show_notification_settings(update, context)
    
    async def _show_symbol_settings(self, update: Update, context: CallbackContext) -> int:
        """Show symbol filtering settings"""
        query = update.callback_query
        user_id = context.user_data['settings_user_id']
        user = self.user_repo.get_by_telegram_id(user_id)
        
        symbols_text = (
            "*📊 Symbol Settings*\n\n"
            f"Allowed symbols: {len(user.allowed_symbols) if user.allowed_symbols else 'All'}\n"
            f"Blocked symbols: {len(user.blocked_symbols)}\n\n"
            "Configure which symbols you want to trade:"
        )
        
        await query.edit_message_text(
            symbols_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_symbol_settings_keyboard(user)
        )
        
        return SYMBOL_SETTINGS
    
    async def handle_symbols(self, update: Update, context: CallbackContext) -> int:
        """Handle symbol settings updates"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('symbol_', '')
        
        if action == 'add':
            await query.edit_message_text(
                "Enter symbol to allow (e.g., EURUSD):"
            )
            context.user_data['awaiting'] = 'add_symbol'
            return CONFIRM_UPDATE
        
        elif action == 'remove':
            await query.edit_message_text(
                "Enter symbol to block:"
            )
            context.user_data['awaiting'] = 'remove_symbol'
            return CONFIRM_UPDATE
        
        elif action == 'clear':
            # Clear all filters
            user_id = context.user_data['settings_user_id']
            user = self.user_repo.get_by_telegram_id(user_id)
            user.allowed_symbols = []
            user.blocked_symbols = []
            self.db.commit()
            
            await query.edit_message_text("✅ Symbol filters cleared.")
            return self._show_symbol_settings(update, context)
        
        elif action == 'back':
            return self._show_symbol_settings(update, context)
    
    async def _show_connection_settings(self, update: Update, context: CallbackContext) -> int:
        """Show connection settings"""
        query = update.callback_query
        user_id = context.user_data['settings_user_id']
        user = self.user_repo.get_by_telegram_id(user_id)
        
        conn_text = (
            "*🔌 Connection Settings*\n\n"
            f"Account: `{user.mt5_account_id}`\n"
            f"Server: {user.mt5_server}\n"
            f"Status: {'✅ Connected' if user.mt_connected else '❌ Disconnected'}\n"
            f"Last connected: {user.last_connected.strftime('%Y-%m-%d %H:%M UTC') if user.last_connected else 'Never'}\n\n"
            "What would you like to do?"
        )
        
        await query.edit_message_text(
            conn_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_connection_settings_keyboard()
        )
        
        return CONNECTION_SETTINGS
    
    async def handle_connection(self, update: Update, context: CallbackContext) -> int:
        """Handle connection settings"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('conn_', '')
        
        if action == 'test':
            await query.edit_message_text("🔄 Testing connection...")
            # Trigger connection test
            asyncio.create_task(self._test_connection(update, context))
            return CONNECTION_SETTINGS
        
        elif action == 'update':
            await query.edit_message_text(
                "Enter new MT5 credentials in format:\n"
                "`ACCOUNT_ID PASSWORD SERVER`\n\n"
                "Example:\n"
                "`123456 MyPassword ICMarkets-Demo`"
            )
            context.user_data['awaiting'] = 'credentials'
            return CONFIRM_UPDATE
        
        elif action == 'back':
            return self._show_connection_settings(update, context)
    
    async def _show_api_settings(self, update: Update, context: CallbackContext) -> int:
        """Show API settings"""
        query = update.callback_query
        user_id = context.user_data['settings_user_id']
        settings = self.settings_repo.get_by_telegram_id(user_id)
        
        api_text = (
            "*🔑 API Access*\n\n"
            f"API enabled: {'✅' if settings.api_enabled else '❌'}\n"
            f"API key: `{settings.api_key or 'Not generated'}`\n\n"
            "Generate an API key to access the bot programmatically."
        )
        
        await query.edit_message_text(
            api_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_api_settings_keyboard(settings)
        )
        
        return API_SETTINGS
    
    async def handle_api(self, update: Update, context: CallbackContext) -> int:
        """Handle API settings"""
        query = update.callback_query
        await query.answer()
        
        action = query.data.replace('api_', '')
        user_id = context.user_data['settings_user_id']
        
        if action == 'generate':
            # Generate new API key
            api_key = self.settings_repo.generate_api_key(user_id)
            await query.edit_message_text(
                f"✅ *New API Key Generated*\n\n"
                f"Key: `{api_key}`\n\n"
                "⚠️ Save this key now - it won't be shown again!\n\n"
                "Use this key in the `X-API-Key` header for API requests.",
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif action == 'revoke':
            # Revoke API key
            self.settings_repo.revoke_api_key(user_id)
            await query.edit_message_text("✅ API key revoked.")
        
        elif action == 'back':
            return self._show_api_settings(update, context)
        
        return API_SETTINGS
    
    async def confirm_update(self, update: Update, context: CallbackContext) -> int:
        """Handle text input for settings updates"""
        if not update.message:
            return CONFIRM_UPDATE
        
        text = update.message.text
        awaiting = context.user_data.get('awaiting')
        user_id = context.user_data['settings_user_id']
        
        if awaiting == 'risk_factor':
            try:
                risk = float(text) / 100
                if 0.001 <= risk <= 0.1:
                    self.user_repo.update_user(user_id, default_risk_factor=risk)
                    await update.message.reply_text(f"✅ Risk factor updated to {float(text):.1f}%")
                else:
                    raise ValueError
            except:
                await update.message.reply_text("❌ Invalid value. Please enter a number between 0.1 and 10.")
                return CONFIRM_UPDATE
        
        elif awaiting == 'max_size':
            try:
                size = float(text)
                if 0.01 <= size <= 100:
                    self.user_repo.update_user(user_id, max_position_size=size)
                    await update.message.reply_text(f"✅ Max position size updated to {size}")
                else:
                    raise ValueError
            except:
                await update.message.reply_text("❌ Invalid value. Please enter a number between 0.01 and 100.")
                return CONFIRM_UPDATE
        
        elif awaiting == 'notify_hour':
            try:
                hour = int(text)
                if 0 <= hour <= 23:
                    settings = self.settings_repo.get_by_telegram_id(user_id)
                    settings.notification_hour = hour
                    self.db.commit()
                    await update.message.reply_text(f"✅ Notification hour set to {hour}:00 UTC")
                else:
                    raise ValueError
            except:
                await update.message.reply_text("❌ Invalid hour. Please enter a number between 0 and 23.")
                return CONFIRM_UPDATE
        
        elif awaiting == 'credentials':
            # Parse credentials
            parts = text.split()
            if len(parts) >= 3:
                account = parts[0]
                password = parts[1]
                server = ' '.join(parts[2:])
                
                # Update in background
                await update.message.reply_text("🔄 Updating credentials...")
                asyncio.create_task(self._update_credentials(update, context, account, password, server))
            else:
                await update.message.reply_text("❌ Invalid format. Use: ACCOUNT PASSWORD SERVER")
                return CONFIRM_UPDATE
        
        # Clear awaiting state
        context.user_data.pop('awaiting', None)
        
        # Return to main menu
        await update.message.reply_text(
            self._format_settings_summary(self.user_repo.get_by_telegram_id(user_id)),
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_settings_keyboard()
        )
        
        return MAIN_MENU
    
    async def _test_connection(self, update: Update, context: CallbackContext):
        """Test MT5 connection"""
        user_id = context.user_data['settings_user_id']
        
        try:
            from services.mt5_manager import MT5ConnectionManager
            mt5 = MT5ConnectionManager(self.db)
            await mt5.get_connection(user_id)
            
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Connection test successful!"
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Connection test failed: {str(e)[:100]}"
            )
    
    async def _update_credentials(self, update: Update, context: CallbackContext,
                                  account: str, password: str, server: str):
        """Update MT5 credentials"""
        user_id = context.user_data['settings_user_id']
        
        from services.mt5_manager import MT5ConnectionManager
        from services.auth import EncryptionService
        
        encryption = EncryptionService()
        encrypted_password = encryption.encrypt(password)
        
        success, message = await MT5ConnectionManager(self.db).connect_user(
            user_id=user_id,
            mt5_account=account,
            mt5_password=encrypted_password,
            mt5_server=server
        )
        
        if success:
            # Update database
            self.user_repo.update_user(
                user_id,
                mt5_account_id=account,
                mt5_password=encrypted_password,
                mt5_server=server
            )
            
            await context.bot.send_message(
                chat_id=user_id,
                text="✅ Credentials updated successfully!"
            )
        else:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"❌ Update failed: {message}"
            )
    
    def _format_settings_summary(self, user) -> str:
        """Format settings summary for display"""
        settings = self.settings_repo.get_by_telegram_id(user.telegram_id)
        
        return (
            "*⚙️ Your Settings*\n\n"
            f"*Risk Management*\n"
            f"• Risk factor: {user.default_risk_factor*100:.1f}%\n"
            f"• Max position: {user.max_position_size} lots\n\n"
            
            f"*Notifications*\n"
            f"• Trade alerts: {'✅' if settings.notify_on_trade else '❌'}\n"
            f"• Error alerts: {'✅' if settings.notify_on_error else '❌'}\n"
            f"• Daily report: {'✅' if settings.notify_daily_report else '❌'} at {settings.notification_hour}:00 UTC\n\n"
            
            f"*Symbols*\n"
            f"• Allowed: {len(user.allowed_symbols) if user.allowed_symbols else 'All'}\n"
            f"• Blocked: {len(user.blocked_symbols)}\n\n"
            
            f"*Connection*\n"
            f"• Status: {'✅ Connected' if user.mt_connected else '❌ Disconnected'}\n"
            f"• Account: `{user.mt5_account_id}`\n\n"
            
            "Select a category to modify:"
        )
    
    async def cancel(self, update: Update, context: CallbackContext) -> int:
        """Cancel settings"""
        await update.message.reply_text("⚙️ Settings closed.")
        context.user_data.clear()
        return ConversationHandler.END

    def get_states(self):
        """Return conversation states using bound instance methods"""
        # Defined after class so SettingsHandler is in scope
        return  {
            MAIN_MENU: [CallbackQueryHandler(self.handle_menu, pattern='^settings_')],
            RISK_SETTINGS: [CallbackQueryHandler(self.handle_risk, pattern='^risk_')],
            NOTIFICATION_SETTINGS: [CallbackQueryHandler(self.handle_notifications, pattern='^notify_')],
            SYMBOL_SETTINGS: [CallbackQueryHandler(self.handle_symbols, pattern='^symbol_')],
            CONNECTION_SETTINGS: [CallbackQueryHandler(self.handle_connection, pattern='^conn_')],
            API_SETTINGS: [CallbackQueryHandler(self.handle_api, pattern='^api_')],
            CONFIRM_UPDATE: [CallbackQueryHandler(self.confirm_update, pattern='^confirm_')],
        }
