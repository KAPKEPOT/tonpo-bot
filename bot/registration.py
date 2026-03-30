# fx/bot/registration.py
import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
from sqlalchemy.orm import Session

from database.repositories import UserRepository
from services.auth import AuthService, EncryptionService
#from services.mt5_manager import MT5ConnectionManager
# MT5ConnectionManager removed — gateway handles MT5 connections now
from services.notification import NotificationService
from core.validators import CredentialsValidator
#from gateway_client import ExecutionProvider, GatewayConfig
from config.settings import settings

logger = logging.getLogger(__name__)

# Conversation states
(ENTER_ACCOUNT, ENTER_PASSWORD, ENTER_SERVER, 
 CONFIRM_CREDENTIALS, VERIFYING, COMPLETE) = range(6)

class RegistrationHandler:
    def __init__(self, db_session: Session, bot, mt5_manager=None):
        self.db = db_session
        self.bot = bot
        self.user_repo = UserRepository(db_session)
        self.auth_service = AuthService(db_session)
        self.encryption = EncryptionService()
        
        # Initialize execution provider
        self.execution_provider = None  # injected by main.py after startup
    
    async def initialize(self):
        """Initialize the execution provider"""
        await self.execution_provider.initialize(self.gateway_config)
    
    async def start(self, update: Update, context: CallbackContext) -> int:
        """Start the registration process"""
        user = update.effective_user

        # Clear any stale conversation state from a previous interrupted session
        context.user_data.clear()

        # Check if already registered
        existing = self.user_repo.get_by_telegram_id(user.id)
        if existing:
            if existing.is_verified:
                await update.message.reply_text(
                    "✅ You are already registered! Use /settings to update your credentials."
                )
                return ConversationHandler.END
            else:
                # Continue with existing unverified user
                context.user_data['user_id'] = existing.id
        
        welcome_text = (
            "🚀 *Let's get you set up!*\n\n"
            "I'll need your MetaTrader 5 credentials to connect to your account.\n\n"
            "⚠️ *Important:*\n"
            "• Your password will be encrypted and stored securely\n"
            "• We recommend using a demo account first\n"
            "• You can change these later in /settings\n\n"
            "Please enter your **MT5 Account ID** (login number):"
        )
        
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN)
        return ENTER_ACCOUNT
    
    async def receive_account(self, update: Update, context: CallbackContext) -> int:
        """Receive and validate account ID"""
        account_id = update.message.text.strip()
        
        # Validate format using CredentialsValidator
        is_valid, error = CredentialsValidator.validate_account_id(account_id)
        if not is_valid:
            await update.message.reply_text(f"❌ {error}\nPlease try again:")
            return ENTER_ACCOUNT
        
        context.user_data['mt5_account'] = account_id
        await update.message.reply_text(
            "✅ Account ID received!\n\n"
            "Now please enter your **MT5 password**:\n"
            "_(Your password will be encrypted)_",
            parse_mode=ParseMode.MARKDOWN
        )
        return ENTER_PASSWORD
    
    async def receive_password(self, update: Update, context: CallbackContext) -> int:
        """Receive and temporarily store password"""
        password = update.message.text
        
        # Basic validation
        is_valid, error = CredentialsValidator.validate_password(password)
        if not is_valid:
            await update.message.reply_text(f"❌ {error}\nPlease try again:")
            return ENTER_PASSWORD
        
        context.user_data['mt5_password'] = password
        await update.message.reply_text(
            "✅ Password received!\n\n"
            "Finally, enter your **MT5 server name**:\n"
            "_(e.g., IC Markets-Demo, ICMarkets-Server, Forex.com-Main)_"
        )
        return ENTER_SERVER
    
    async def receive_server(self, update: Update, context: CallbackContext) -> int:
        """Receive server and show confirmation"""
        server = update.message.text.strip()
        
        # Validate server format using CredentialsValidator
        is_valid, error = CredentialsValidator.validate_server(server)
        if not is_valid:
            await update.message.reply_text(f"❌ {error}\nPlease try again:")
            return ENTER_SERVER
        
        context.user_data['mt5_server'] = server
        
        # Show confirmation
        from bot.keyboards import get_confirmation_keyboard
        
        confirm_text = (
            "*Please confirm your credentials:*\n\n"
            f"Account ID: `{context.user_data['mt5_account']}`\n"
            f"Server: {server}\n"
            f"Password: {'•' * len(context.user_data['mt5_password'])}\n\n"
            "Is this correct?"
        )
        
        await update.message.reply_text(
            confirm_text,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_confirmation_keyboard()
        )
        return CONFIRM_CREDENTIALS
    
    async def confirm_credentials(self, update: Update, context: CallbackContext) -> int:
        """Handle confirmation callback"""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'confirm_yes':
            await query.edit_message_text(
                "🔄 *Verifying your credentials...*\n"
                "This may take up to 30 seconds.",
                parse_mode=ParseMode.MARKDOWN
            )
            
            # Start verification
            return await self._verify_credentials(update, context)
        else:
            await query.edit_message_text(
                "❌ Registration cancelled. Use /register to start over."
            )
            return ConversationHandler.END
    
    async def _verify_credentials(self, update: Update, context: CallbackContext) -> int:
    	"""Send credentials to CMG, store only what comes back"""
    	user_id = update.effective_user.id
    	query = update.callback_query
    	
    	# Pull from memory — will be wiped immediately after use
    	account  = context.user_data.pop('mt5_account')
    	password = context.user_data.pop('mt5_password')
    	server   = context.user_data.pop('mt5_server')
    	
    	try:
    		if not self.execution_provider:
    			raise RuntimeError("Gateway not available — please try again later")
    			
    		# Forward to CMG — bot never touches these again after this call
    		success, message, creds = await self.execution_provider.register_user(
    		    telegram_id=user_id,
    		    mt5_account=account,
    		    mt5_password=password,
    		    mt5_server=server,
    		)
    		# Wipe from memory immediately — CMG owns them now
    		del account, password, server
    		
    		if not success:
    			raise RuntimeError(message)
    		
    		# Bot only stores the routing keys
    		gateway_api_key    = creds['gateway_api_key']
    		gateway_account_id = creds['gateway_account_id']
    		
    		existing = self.user_repo.get_by_telegram_id(user_id)
    		if existing:
    			self.user_repo.update_user(
    			    user_id,
    			    is_verified=True,
    			    mt_connected=True,
    			    gateway_api_key=gateway_api_key,
    			    gateway_account_id=gateway_account_id,
    			)
    		else:
    			self.user_repo.create_user(
    			    telegram_id=user_id,
    			    telegram_username=update.effective_user.username,
    			    first_name=update.effective_user.first_name,
    			    last_name=update.effective_user.last_name,
    			    is_verified=True,
    			    mt_connected=True,
    			    gateway_api_key=gateway_api_key,
    			    gateway_account_id=gateway_account_id,
    			)
    			
    		# Show success + risk selection
    		from bot.keyboards import get_risk_keyboard
    		await query.edit_message_text(
    		    "✅ *Account connected successfully!*\n\n"
    		    "Status: 🟢 Active\n\n"
    		    "Now, let's set your default risk per trade:",	    
    		    parse_mode=ParseMode.MARKDOWN,
    		    reply_markup=get_risk_keyboard()
    		)
    		return COMPLETE
    	
    	except Exception as e:
    		error_str = str(e)
    		logger.error(f"Registration failed for user {user_id}: {error_str}")
    		
    		# Clean up any partial DB state
    		try:
    			self.user_repo.update_user(
    			    user_id,
    			    gateway_api_key=None,
    			    gateway_account_id=None,
    			    is_verified=False,
    			    mt_connected=False,
    			)
    		except Exception:
    			pass
    		
    		# Strip raw HTML from gateway/nginx errors
    		user_msg = "Gateway connection error. Please try again later." \
            if '<html>' in error_str.lower() else error_str[:150]
    		await query.edit_message_text(
    		    f"❌ *Registration error*\n\n{user_msg}\n\n"
    		    "Please check your credentials and try /register again.",
    		    parse_mode=ParseMode.MARKDOWN
    		)
    		context.user_data.clear()
    		return ConversationHandler.END
    			
    async def complete(self, update: Update, context: CallbackContext) -> int:
        """Complete registration with risk preference"""
        query = update.callback_query
        await query.answer()
        
        if query.data.startswith('risk_'):
            # Parse risk percentage
            risk_str = query.data.replace('risk_', '')
            if risk_str == 'custom':
                await query.edit_message_text(
                    "Please enter your custom risk percentage (e.g., 1.5 for 1.5%):"
                )
                return COMPLETE
            else:
                risk = float(risk_str) / 100
        else:
            # Custom risk input
            try:
                risk = float(update.message.text) / 100
                if risk < 0.001 or risk > 0.1:
                    raise ValueError
            except:
                await update.message.reply_text(
                    "❌ Invalid risk percentage. Please enter a number between 0.1 and 10:"
                )
                return COMPLETE
        
        # Save risk preference
        user_id = update.effective_user.id
        self.user_repo.update_user(user_id, default_risk_factor=risk)
        
        # Clear sensitive data
        context.user_data.clear()
        
        # Send completion message
        completion_text = (
            "🎉 *Registration Complete!* 🎉\n\n"
            f"Your default risk is set to *{risk*100:.1f}%*\n\n"
            "*Next steps:*\n"
            "• Use /trade to place your first trade\n"
            "• Use /settings to customize preferences\n"
            "• Use /help to see all commands\n\n"
            "Happy trading! 📈"
        )
        
        if hasattr(update, 'callback_query'):
            await query.edit_message_text(completion_text, parse_mode=ParseMode.MARKDOWN)
        else:
            await update.message.reply_text(completion_text, parse_mode=ParseMode.MARKDOWN)
        
        return ConversationHandler.END
    
    async def cancel(self, update: Update, context: CallbackContext) -> int:
        """Cancel registration"""
        await update.message.reply_text(
            "❌ Registration cancelled. Use /register to start over."
        )
        
        # Clear any stored data
        context.user_data.clear()
        
        return ConversationHandler.END

    def get_states(self):
        """Return conversation states using bound instance methods"""
        # Defined after class so RegistrationHandler is in scope
        return  {
            ENTER_ACCOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_account)],
            ENTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_password)],
            ENTER_SERVER: [MessageHandler(filters.TEXT & ~filters.COMMAND, self.receive_server)],
            CONFIRM_CREDENTIALS: [CallbackQueryHandler(self.confirm_credentials, pattern='^confirm_')],
            VERIFYING: [],  # No input while verifying
            COMPLETE: [
                CallbackQueryHandler(self.complete, pattern='^risk_'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, self.complete),
            ],
        }