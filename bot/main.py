# fx/bot/main.py
import logging
import asyncio
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, PicklePersistence
)

from config.settings import settings
from database.database import db_manager
from bot.handlers import CommandHandlers
from bot.registration import RegistrationHandler
from bot.trading import TradingHandler
from bot.settings import SettingsHandler
from bot.admin import AdminHandler
from bot.middleware import AuthMiddleware, RateLimitMiddleware, ErrorHandler
from services.mt5_manager import MT5ConnectionManager
from services.notification import NotificationService
from services.cache import CacheService
from services.queue import QueueService, AsyncTaskManager
from services.monitoring import MonitoringService

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
        self.mt5_manager = None  # created in _post_init (needs running event loop)

        # Initialize all handler objects synchronously — no async needed yet
        self.command_handlers = CommandHandlers(self.db, None)   # bot set after build
        self.registration     = RegistrationHandler(self.db, None, mt5_manager=None)
        self.trading          = TradingHandler(self.db, None, mt5_manager=None)
        self.settings_handler = SettingsHandler(self.db, None)
        self.admin            = AdminHandler(self.db, None)
        self.auth_middleware  = AuthMiddleware(self.db)
        self.rate_limiter     = RateLimitMiddleware(self.cache)

        # Build application — handlers registered BEFORE build() via pre_init isn't
        # available, so we build first then add_handler before initialize() is called
        persistence = PicklePersistence(filepath='bot_persistence')
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

        # Register all handlers NOW — before initialize() is called by run_polling()
        self._setup_middleware()
        self._setup_handlers()

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
            fallbacks=[CommandHandler("cancel", self.registration.cancel)],
            name="registration",
            persistent=True,
            per_message=False,
        )
        app.add_handler(reg_conv)

        # Trading conversation
        trade_conv = ConversationHandler(
            entry_points=[CommandHandler("trade", self.auth_middleware.wrap(self.trading.start_trade))],
            states=self.trading.get_states(),
            fallbacks=[CommandHandler("cancel", self.trading.cancel)],
            name="trading",
            persistent=True,
            per_message=False,
        )
        app.add_handler(trade_conv)

        # Calculate conversation
        calc_conv = ConversationHandler(
            entry_points=[CommandHandler("calculate", self.auth_middleware.wrap(self.trading.start_calculate))],
            states=self.trading.get_states(),
            fallbacks=[CommandHandler("cancel", self.trading.cancel)],
            name="calculate",
            persistent=True,
            per_message=False,
        )
        app.add_handler(calc_conv)

        # Settings conversation
        settings_conv = ConversationHandler(
            entry_points=[CommandHandler("settings", self.auth_middleware.wrap(self.settings_handler.start))],
            states=self.settings_handler.get_states(),
            fallbacks=[CommandHandler("cancel", self.settings_handler.cancel)],
            name="settings",
            persistent=True,
            per_message=False,
        )
        app.add_handler(settings_conv)

        # Admin commands
        app.add_handler(CommandHandler("admin",     self.auth_middleware.wrap_admin(self.admin.dashboard)))
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
        app.add_handler(CallbackQueryHandler(self._handle_callback, pattern="^[a-z_]+:"))

    async def _post_init(self, application):
        """Called by PTB after event loop starts — safe for async init only"""
        logger.info("Initializing async services...")

        # MetaApi requires a running event loop
        self.mt5_manager = MT5ConnectionManager(self.db)
        await self.mt5_manager.start()

        # Inject shared mt5_manager into handlers that need it
        self.registration.mt5_manager = self.mt5_manager
        self.trading.mt5_manager = self.mt5_manager
        if hasattr(self.trading, 'trade_executor') and self.trading.trade_executor:
            self.trading.trade_executor.mt5_manager = self.mt5_manager

        # Set bot commands
        await self.bot.set_my_commands([
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
        ])

        # Schedule background tasks — use application.create_task so PTB tracks them
        application.create_task(self._background_tasks())

        logger.info("Bot initialized successfully")

    async def _post_shutdown(self, application):
        logger.info("Shutting down services...")
        if self.mt5_manager:
            await self.mt5_manager.stop()
        self.db.close()
        logger.info("Bot stopped")

    async def _handle_callback(self, update, context):
        query = update.callback_query
        parts = query.data.split(':')
        handler_name = parts[0]

        if handler_name == 'trade':
            await self.trading.handle_callback(update, context)
        elif handler_name == 'settings':
            await self.settings_handler.handle_callback(update, context)
        elif handler_name == 'admin':
            await self.admin.handle_callback(update, context)
        else:
            await query.answer("Unknown action")

    async def _background_tasks(self):
        async def run_every(coro_fn, seconds):
            while True:
                await asyncio.sleep(seconds)
                try:
                    await coro_fn()
                except Exception as e:
                    logger.error(f"Background task error: {e}")

        async def process_expired():
            from services.subscription import SubscriptionService
            sub_service = SubscriptionService(self.db)
            count = sub_service.process_expired()
            if count > 0:
                logger.info(f"Processed {count} expired subscriptions")

        async def collect_metrics():
            self.monitoring.collect_metrics()

        await asyncio.gather(
            run_every(self._check_connections, 300),
            run_every(collect_metrics, 900),
            run_every(process_expired, 86400),
        )

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
            self.application.run_polling()
