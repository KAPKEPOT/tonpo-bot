# fx/bot/main.py
import logging
import asyncio
import warnings
from telegram.warnings import PTBUserWarning
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler
)

from config.settings import settings
from database.database import db_manager
from bot.handlers import CommandHandlers
from database.repositories import UserRepository
from services.subscription import SubscriptionService
from bot.registration import RegistrationHandler
from bot.trading import TradingHandler
from bot.settings import SettingsHandler
from bot.admin import AdminHandler
from bot.middleware import AuthMiddleware, RateLimitMiddleware, ErrorHandler
#from services.mt5_manager import MT5ConnectionManager
from services.notification import NotificationService
from services.cache import CacheService
from services.queue import QueueService, AsyncTaskManager
from services.monitoring import MonitoringService
from database.db_persistence import DBPersistence
from gateway_client import ExecutionProvider

logger = logging.getLogger(__name__)

class Bot:
    """
    Main bot class - initializes and runs the Telegram bot
    """

    def __init__(self):
        # Initialize database
        db_manager.initialize(settings.DATABASE_URL)
        self.db = db_manager.get_session()
        
        # Initialize sync services
        self.cache = CacheService()
        self.queue = QueueService()
        self.task_manager = AsyncTaskManager()
        self.notification = NotificationService(self.db, None)
        self.monitoring = MonitoringService(self.db)
        self.mt5_manager = None 
        # Initialize all handler objects synchronously — no async needed yet
        self.command_handlers = CommandHandlers(self.db, None)   # bot set after build
        self.user_repo = UserRepository(self.db)
        self.sub_service = SubscriptionService(self.db)
        self.registration     = RegistrationHandler(self.db, None, mt5_manager=None)
        self.trading          = TradingHandler(self.db, None, mt5_manager=None)
        self.settings_handler = SettingsHandler(self.db, None)
        self.admin            = AdminHandler(self.db, None)
        self.auth_middleware  = AuthMiddleware(self.db)
        self.rate_limiter     = RateLimitMiddleware(self.cache)

        # Build application — handlers registered BEFORE build() via pre_init isn't
        # available, so we build first then add_handler before initialize() is called
        persistence = DBPersistence()
        self.application = (
            ApplicationBuilder()
            .token(settings.BOT_TOKEN)
            .persistence(persistence)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )

        # bot reference is available after build()
        self.bot = self.application.bot
        self.notification.bot        = self.bot
        self.command_handlers.bot    = self.bot
        self.registration.bot        = self.bot
        self.trading.bot             = self.bot
        self.settings_handler.bot    = self.bot
        self.admin.bot               = self.bot

        # Error handler needs notification + monitoring (both sync-ready)
        self.error_handler = ErrorHandler(self.notification, self.monitoring)

        # Suppress expected per_message warning — our conversations intentionally
        # mix MessageHandler and CallbackQueryHandler states, making per_message=False correct.
        warnings.filterwarnings('ignore', message=".*per_message=False.*", category=PTBUserWarning)

        # Register all handlers NOW — before initialize() is called by run_polling()
        self._setup_middleware()
        self._setup_handlers()
        
        # Initialize execution provider
        self.execution_provider = ExecutionProvider(use_gateway=settings.USE_GATEWAY)

    def _setup_middleware(self):
        self.application.add_error_handler(self.error_handler.handle)

    def _setup_handlers(self):
        app = self.application

        # Basic commands (no auth)
        app.add_handler(CommandHandler("start", self.command_handlers.start))
        app.add_handler(CommandHandler("help",  self.command_handlers.help))
        app.add_handler(CommandHandler("about", self.command_handlers.about))

        # Registration conversation
        reg_conv = ConversationHandler(
            entry_points=[CommandHandler("register", self.registration.start)],
            states=self.registration.get_states(),
            fallbacks=[
                CommandHandler("cancel", self.registration.cancel),
                CommandHandler("register", self.registration.start),  # allow restart
            ],
            name="registration",
            persistent=True,
            per_message=False,
            allow_reentry=True,
        )
        app.add_handler(reg_conv)

        # Trading conversation
        trade_conv = ConversationHandler(
            entry_points=[CommandHandler("trade", self.auth_middleware.wrap(self.trading.start_trade))],
            states=self.trading.get_states(),
            fallbacks=[
                CommandHandler("cancel", self.trading.cancel),
                CommandHandler("trade", self.auth_middleware.wrap(self.trading.start_trade)),
            ],
            name="trading",
            persistent=True,
            per_message=False,
            allow_reentry=True,
        )
        app.add_handler(trade_conv)

        # Calculate conversation
        calc_conv = ConversationHandler(
            entry_points=[CommandHandler("calculate", self.auth_middleware.wrap(self.trading.start_calculate))],
            states=self.trading.get_states(),
            fallbacks=[
                CommandHandler("cancel", self.trading.cancel),
                CommandHandler("calculate", self.auth_middleware.wrap(self.trading.start_calculate)),
            ],
            name="calculate",
            persistent=True,
            per_message=False,
            allow_reentry=True,
        )
        app.add_handler(calc_conv)

        # Settings conversation
        settings_conv = ConversationHandler(
            entry_points=[CommandHandler("settings", self.auth_middleware.wrap(self.settings_handler.start))],
            states=self.settings_handler.get_states(),
            fallbacks=[
                CommandHandler("cancel", self.settings_handler.cancel),
                CommandHandler("settings", self.auth_middleware.wrap(self.settings_handler.start)),
            ],
            name="settings",
            persistent=True,
            per_message=False,
            allow_reentry=True,
        )
        app.add_handler(settings_conv)

        # Admin commands
        admin_conv = ConversationHandler(
            entry_points=[
                CommandHandler("admin", self.auth_middleware.wrap_admin(self.admin.dashboard))
            ],
            states=self.admin.get_states(),
            fallbacks=[
                CommandHandler("cancel", self.admin.cancel),
                CommandHandler("admin", self.auth_middleware.wrap_admin(self.admin.dashboard)),
            ],
            name="admin",
            persistent=True,
            per_message=False,
            allow_reentry=True,
        )
        app.add_handler(admin_conv)
        
        # Quick admin commands (work outside conversation)
        app.add_handler(CommandHandler("stats",     self.auth_middleware.wrap_admin(self.admin.stats)))
        app.add_handler(CommandHandler("broadcast", self.auth_middleware.wrap_admin(self.admin.broadcast)))

        # Authenticated commands
        for cmd, handler in [
            ("balance",   self.command_handlers.balance),
            ("positions", self.command_handlers.positions),
            ("history",   self.command_handlers.history),
            ("profile",   self.command_handlers.profile),
            ("upgrade",   self.command_handlers.upgrade),
        ]:
            app.add_handler(CommandHandler(cmd, self.auth_middleware.wrap(handler)))

        # Callback query router
        app.add_handler(CallbackQueryHandler(self._handle_callback))

    async def _post_init(self, application):
        """Called by PTB after event loop starts — safe for async init only"""
        logger.info("Initializing async services...")
        
        # Always initialize gateway
        try:
        	await self.execution_provider.initialize(settings.gateway_config)
        	self._load_gateway_credentials()
        	logger.info("Gateway initialized successfully")
        except Exception as e:
        	logger.error(f"Gateway initialization failed: {e}")

        # Inject into handlers regardless of gateway success/failure
        self.registration.execution_provider = self.execution_provider
        self.trading.execution_provider = self.execution_provider
        self.trading.mt5_manager_ready.set()
        self.settings_handler.execution_provider = self.execution_provider
        
        if hasattr(self.trading, 'trade_executor') and self.trading.trade_executor:
        	self.trading.trade_executor.mt5_manager = self.trading.mt5_manager
        
        from telegram import BotCommandScopeChat
        # Default commands (all users)
        user_commands = [
            BotCommand("start",     "Start the bot"),
            BotCommand("help",      "Show help"),
            BotCommand("register",  "Register your MT5 account"),
            BotCommand("trade",     "Place a trade"),
            BotCommand("calculate", "Calculate risk without trading"),
            BotCommand("balance",   "Check account balance"),
            BotCommand("positions", "View open positions"),
            BotCommand("history",   "View trade history"),
            BotCommand("settings",  "Configure settings"),
            BotCommand("profile",   "View your profile"),
            BotCommand("upgrade",   "Upgrade subscription"),
        ]
        await self.bot.set_my_commands(user_commands)
        
        # Admin commands (only visible to admins)
        admin_commands = user_commands + [
            BotCommand("admin",     "👑 Admin dashboard"),
            BotCommand("stats",     "👑 System stats"),
            BotCommand("broadcast", "👑 Broadcast message"),
        ]
        
        for admin_id in settings.ADMIN_USER_IDS:
            try:
                await self.bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=admin_id)
                )
            except Exception as e:
                logger.warning(f"Could not set admin commands for {admin_id}: {e}")

        # Schedule background tasks via job_queue (runs after polling starts, not during init)
        application.job_queue.run_once(
            lambda ctx: asyncio.ensure_future(self._background_tasks()),
            when=0,
            name="background_tasks"
        )

        logger.info("Bot initialized successfully")


    async def _post_shutdown(self, application):
        """Shut down all services — fast and clean"""
        logger.info("Shutting down...")

        # 1. Cancel all background tasks immediately
        tasks = [t for t in asyncio.all_tasks()
                 if t is not asyncio.current_task() and not t.done()]

        for task in tasks:
            task.cancel()

        if tasks:
            # Give tasks 2 seconds to finish, then move on
            done, pending = await asyncio.wait(tasks, timeout=2.0)
            if pending:
                logger.warning(f"{len(pending)} tasks didn't stop in time — forcing")

        # 2. Stop MT5 connection manager
        if self.mt5_manager:
            try:
                await asyncio.wait_for(self.mt5_manager.stop(), timeout=2.0)
            except Exception:
                pass

        # 3. Close Redis/cache
        if hasattr(self, 'cache') and self.cache:
            try:
                await self.cache.close()
            except Exception:
                pass

        # 4. Close database
        if self.db:
            try:
                self.db.close()
            except Exception:
                pass

        logger.info("Bot stopped successfully")

        # 5. Force exit — prevents any lingering connections from hanging
        import os
        os._exit(0)

    async def _handle_callback(self, update, context):
        query = update.callback_query
        user_id = update.effective_user.id
        data = query.data
        
        logger.debug(f"Callback received: {data} from user {user_id}")
        
        if data.startswith('admin:') or data.startswith('admin_') or data.startswith('user_'):
        	# Verify admin status
        	if user_id not in settings.ADMIN_USER_IDS:
        		await query.answer("❌ Admin access required", show_alert=True)
        		logger.warning(f"Non-admin user {user_id} attempted admin action: {data}")
        		return
        		
        	# Call the admin handler's callback method
        	await self.admin.handle_callback(update, context)
        	logger.info(f"Admin action {data} executed by user {user_id}")
        
        elif data.startswith('trade_') or data.startswith('trade:'):
        	# Verify user is registered and active
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first using /register", show_alert=True)
        		return
        	if not user.is_active:
        		await query.answer("❌ Your account is deactivated", show_alert=True)
        		return
        	if user.is_banned:
        		await query.answer("❌ Your account has been banned", show_alert=True)
        		return
        		
        	# Forward to trading handler's confirm_trade method
        	await self.trading.confirm_trade(update, context)
        
        elif data.startswith('settings_') or data.startswith('settings:'):
        	# Verify user is registered and active
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first using /register", show_alert=True)
        		return
        	if not user.is_active:
        		await query.answer("❌ Your account is deactivated", show_alert=True)
        		return
        	if user.is_banned:
        		await query.answer("❌ Your account has been banned", show_alert=True)
        		return
        	
        	# Forward to settings handler's handle_menu method
        	await self.settings_handler.handle_menu(update, context)
        
        elif data.startswith('confirm_'):
        	# Registration doesn't require auth check (user might not be registered yet)
        	await self.registration.confirm_credentials(update, context)
        
        elif data.startswith('plan_'):
        	# Can be accessed by anyone, but check registration for upgrades
        	if data in ['plan_free', 'plan_basic', 'plan_pro', 'plan_enterprise']:
        		# For plan selection, user should be registered
        		user = self.user_repo.get_by_telegram_id(user_id)
        		if not user:
        			await query.answer("❌ Please register first", show_alert=True)
        			return
        		
        		from bot.callbacks import CallbackHandlers
        		callbacks = CallbackHandlers(self.db, self.bot)
        		tier = data.replace('plan_', '')
        		await callbacks.handle_plan(update, context, ['select', tier])
        	else:
        		await query.answer("Unknown plan action")
        
        elif data.startswith('pay_') or data.startswith('period_'):
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first", show_alert=True)
        		return
        	await self._handle_payment_callback(update, context, data, user)
        
        # Handle notification interactions
        elif data.startswith('notification_') or data.startswith('notify_'):
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first", show_alert=True)
        		return
        	
        	from bot.callbacks import CallbackHandlers
        	callbacks = CallbackHandlers(self.db, self.bot)
        	
        	# Parse action
        	if data.startswith('notification_'):
        		action = data.replace('notification_', '')
        		
        	else:
        		action = data.replace('notify_', '')
        		
        	await callbacks.handle_notification(update, context, [action])
        
        elif data.startswith('position_'):
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first", show_alert=True)
        		return
        	
        	from bot.callbacks import CallbackHandlers
        	callbacks = CallbackHandlers(self.db, self.bot)
        	
        	# Parse action and position ID
        	parts = data.split('_')
        	if len(parts) >= 3:
        		action = parts[1]
        		position_id = '_'.join(parts[2:])  # Rejoin in case ID has underscores
        		await callbacks.handle_position(update, context, [action, position_id])
        	else:
        		await query.answer("Invalid position data")
        
        # Handle pagination (trade history, notifications list)
        elif '_page_' in data:
        	# Extract prefix and page number
        	parts = data.split('_page_')
        	if len(parts) == 2:
        		prefix = parts[0]
        		page = parts[1]
        		
        		from bot.callbacks import CallbackHandlers
        		callbacks = CallbackHandlers(self.db, self.bot)
        		await callbacks.handle_pagination(update, context, [prefix, page])
        	else:
        		await query.answer("Invalid pagination data")
        
        # Handle help section navigation
        elif data.startswith('help_'):
        	from bot.callbacks import CallbackHandlers
        	callbacks = CallbackHandlers(self.db, self.bot)
        	
        	section = data.replace('help_', '')
        	await callbacks.handle_help(update, context, [section])
        
        elif data.startswith('conn_') or data.startswith('api_'):
        	user = self.user_repo.get_by_telegram_id(user_id)
        	if not user:
        		await query.answer("❌ Please register first", show_alert=True)
        		return
        	if not user.is_active:
        		await query.answer("❌ Your account is deactivated", show_alert=True)
        		return
        	if user.is_banned:
        		await query.answer("❌ Your account has been banned", show_alert=True)
        		return
        	# settings_user_id may be absent if user is outside the conversation
        	context.user_data.setdefault('settings_user_id', user_id)
        	if data.startswith('conn_'):
        		await self.settings_handler.handle_connection(update, context)
        	else:
        		await self.settings_handler.handle_api(update, context)
        
        else:
        	logger.warning(f"Unknown callback data received: {data} from user {user_id}")
        	await query.answer("Unknown action", show_alert=False)
        
    async def _handle_payment_callback(self, update, context, data, user):
        query = update.callback_query
        user_id = update.effective_user.id
        
        from services.payment import PaymentService
        from bot.keyboards import get_payment_pending_keyboard, get_upgrade_keyboard
        payment_service = PaymentService(self.db)
        
        # Handle billing period selection
        if data.startswith('period_monthly_') or data.startswith('period_yearly_'):
            parts = data.split('_', 2)
            period = parts[1]  # 'monthly' or 'yearly'
            plan_tier = parts[2]
            
            # Store in context for next step
            context.user_data['upgrade_period'] = period
            context.user_data['upgrade_plan'] = plan_tier
            
            plan = self.sub_service.get_plan(plan_tier)
            price = plan.price_yearly if period == 'yearly' else plan.price_monthly
            
            await query.edit_message_text(
                f"*{plan_tier.title()} Plan — {period.title()}*\\n\\n"
                f"💰 Price: ${price}\\n\\n"
                f"Choose payment method:",
                parse_mode='Markdown',
                reply_markup=get_upgrade_keyboard(plan_tier)
            )
            return
        
        # Handle currency selection → create payment
        if data.startswith('pay_usdt_') or data.startswith('pay_btc_'):
            parts = data.split('_', 2)
            currency = parts[1].upper()
            plan_tier = parts[2]
            period = context.user_data.get('upgrade_period', 'monthly')
            
            try:
                result = payment_service.create_payment_request(
                    user_id=user_id,
                    plan_tier=plan_tier,
                    billing_period=period,
                    currency=currency
                )
                
                network_name = 'Ethereum (ERC-20)' if currency == 'USDT' else 'Bitcoin'
                
                await query.edit_message_text(
                    f"💳 *Payment Request Created*\\n\\n"
                    f"*Plan:* {plan_tier.title()} ({period})\\n"
                    f"*Amount:* `{result['amount']}` {currency}\\n"
                    f"*Network:* {network_name}\\n\\n"
                    f"*Send exactly this amount to:*\\n"
                    f"`{result['wallet_address']}`\\n\\n"
                    f"⚠️ *Send EXACTLY `{result['amount']}` {currency}*\\n"
                    f"The unique amount identifies your payment.\\n\\n"
                    f"⏰ Expires in {result['expires_in_minutes']} minutes\\n\\n"
                    f"Your plan will activate automatically once "
                    f"the transaction is confirmed on-chain.",
                    parse_mode='Markdown',
                    reply_markup=get_payment_pending_keyboard(result['payment_id'])
                )
                
            except Exception as e:
                await query.edit_message_text(f"❌ Error creating payment: {e}")
            return
        
        # Handle check status
        if data.startswith('pay_check_'):
            payment_id = data.replace('pay_check_', '')
            pending = payment_service.get_pending_payment(user_id)
            
            if not pending:
                await query.edit_message_text(
                    "✅ No pending payment found.\\n\\n"
                    "Your plan may have already been activated, "
                    "or the payment expired.\\n\\n"
                    "Use /upgrade to try again."
                )
            else:
                await query.answer(
                    f"⏳ Still waiting... {pending['minutes_left']} min left",
                    show_alert=True
                )
            return
        
        # Handle cancel
        if data.startswith('pay_cancel_'):
            payment_service._cancel_pending(user.id)
            await query.edit_message_text(
                "❌ Payment cancelled.\\n\\nUse /upgrade to try again."
            )
            return
            
    async def _background_tasks(self):
        """Run background tasks with proper cancellation handling"""
        async def run_every(coro_fn, seconds):
        	try:
        		while True:
        			try:
        				await asyncio.sleep(seconds)
        				await coro_fn()
        			except asyncio.CancelledError:
        				logger.info(f"Background task {coro_fn.__name__} cancelled")
        				break
        			except Exception as e:
        				logger.error(f"Background task error in {coro_fn.__name__}: {e}")
        				await asyncio.sleep(5)  # Prevent tight loop on error
        	except asyncio.CancelledError:
        		logger.info(f"run_every task cancelled")
        		raise

        async def process_expired():
            try:
            	from services.subscription import SubscriptionService
            	sub_service = SubscriptionService(self.db)
            	count = sub_service.process_expired(notification_service=self.notification)
            	if count > 0:
            		logger.info(f"Processed {count} expired subscriptions")
            except Exception as e:
            	logger.error(f"Error processing expired subscriptions: {e}")

        async def collect_metrics():
        	try:
        		self.monitoring.collect_metrics()
        	except Exception as e:
        		logger.error(f"Error collecting metrics: {e}")
        
        async def check_expiry_warnings():
        	try:
        		await self.notification.check_subscription_expiry()
        	except Exception as e:
        		logger.error(f"Error checking subscription expiry: {e}")
        
        # Create tasks with names for better tracking
        tasks = [
            asyncio.create_task(run_every(self._check_connections, 300), name="check_connections"),
            asyncio.create_task(run_every(collect_metrics, 900), name="collect_metrics"),
            asyncio.create_task(run_every(process_expired, 86400), name="process_expired"),
            asyncio.create_task(run_every(check_expiry_warnings, 43200), name="check_expiry_warnings"),
        ]
        
        try:
        	# Wait for all tasks, but allow cancellation
        	await asyncio.gather(*tasks)
        except asyncio.CancelledError:
        	logger.info("Background tasks cancelled, cleaning up...")
        	# Cancel all tasks properly
        	for task in tasks:
        		if not task.done():
        			task.cancel()
        	# Wait for tasks to complete cancellation
        	await asyncio.gather(*tasks, return_exceptions=True)
        	raise

    async def _check_connections(self):
        from database.repositories import UserRepository
        repo = UserRepository(self.db)
        users = repo.get_users_needing_connection_check(minutes=30)
        for user in users:
            try:
                await self.mt5_manager.get_connection(user.telegram_id)
            except Exception as e:
                logger.warning(f"Connection check failed for user {user.telegram_id}: {e}")
                await self.notification.send_telegram(
                    user.telegram_id,
                    "⚠️ *Connection Alert*\n\nUnable to connect to your MT5 account. "
                    "Please check your credentials in /settings",
                    parse_mode='Markdown'
                )
    def _load_gateway_credentials(self):
    	"""Load stored gateway credentials from database into GatewayManager"""
    	if not self.execution_provider or not self.execution_provider.gateway_manager:
    		return
    		
    	from database.repositories import UserRepository
    	user_repo = UserRepository(self.db)
    	gateway_users = user_repo.get_gateway_users()
    	
    	loaded = 0
    	for user in gateway_users:
    		try:
    			self.execution_provider.gateway_manager.load_user_credentials(
    			    telegram_id=user.telegram_id,
    			    api_key=user.gateway_api_key,
    			    gateway_user_id=user.gateway_user_id
    			)
    			loaded += 1
    		except Exception as e:
    			logger.warning(f"Failed to load gateway credentials for user {user.telegram_id}: {e}")
    			
    	logger.info(f"Loaded gateway credentials for {loaded} users")
    	
    def run(self):
        """Start the bot — PTB manages the event loop entirely"""
        if settings.USE_WEBHOOK:
            self.application.run_webhook(
                listen="0.0.0.0",
                port=settings.PORT,
                url_path=settings.BOT_TOKEN,
                webhook_url=f"{settings.APP_URL}/{settings.BOT_TOKEN}",
            )
        else:
            self.application.run_polling(
                allowed_updates=None,
                drop_pending_updates=False,
            )