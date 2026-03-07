# fx/bot/main.py
import logging
import asyncio
from telegram import BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ConversationHandler, PicklePersistence
)
from sqlalchemy.orm import Session

from config.settings import settings
from database.database import db_manager
from bot.handlers import CommandHandlers
from bot.registration import RegistrationHandler, REGISTRATION_STATES
from bot.trading import TradingHandler, TRADING_STATES
from bot.settings import SettingsHandler, SETTINGS_STATES
from bot.admin import AdminHandler, ADMIN_STATES
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

        # Initialize services (MetaApi instantiated later inside async context)
        self.cache = CacheService()
        self.queue = QueueService()
        self.task_manager = AsyncTaskManager()
        self.notification = NotificationService(self.db, None)  # Bot set later
        self.monitoring = MonitoringService(self.db)

        # Build PTB v20 Application
        persistence = PicklePersistence(filepath='bot_persistence')
        self.application = (
            ApplicationBuilder()
            .token(settings.BOT_TOKEN)
            .persistence(persistence)
            .build()
        )
        self.bot = self.application.bot

        # Set notification service bot reference
        self.notification.bot = self.bot

        # mt5_manager created in async start() so MetaApi has a running loop
        self.mt5_manager = None

    def _init_handlers(self):
        """Initialize and register all handlers (called after mt5_manager is ready)"""
        self.command_handlers = CommandHandlers(self.db, self.bot)
        self.registration = RegistrationHandler(self.db, self.bot)
        self.trading = TradingHandler(self.db, self.bot)
        self.settings_handler = SettingsHandler(self.db, self.bot)
        self.admin = AdminHandler(self.db, self.bot)

        self.auth_middleware = AuthMiddleware(self.db)
        self.rate_limiter = RateLimitMiddleware(self.cache)
        self.error_handler = ErrorHandler(self.notification, self.monitoring)

        self._setup_middleware()
        self._setup_handlers()
        self._setup_commands()

    def _setup_middleware(self):
        self.application.add_error_handler(self.error_handler.handle)

    def _setup_handlers(self):
        app = self.application

        # Basic commands (no auth)
        app.add_handler(CommandHandler("start", self.command_handlers.start))
        app.add_handler(CommandHandler("help", self.command_handlers.help))
        app.add_handler(CommandHandler("about", self.command_handlers.about))

        # Registration conversation
        reg_conv = ConversationHandler(
            entry_points=[CommandHandler("register", self.registration.start)],
            states=REGISTRATION_STATES,
            fallbacks=[CommandHandler("cancel", self.registration.cancel)],
            name="registration",
            persistent=True,
        )
        app.add_handler(reg_conv)

        # Trading conversation
        trade_conv = ConversationHandler(
            entry_points=[CommandHandler("trade", self.auth_middleware.wrap(self.trading.start_trade))],
            states=TRADING_STATES,
            fallbacks=[CommandHandler("cancel", self.trading.cancel)],
            name="trading",
            persistent=True,
        )
        app.add_handler(trade_conv)

        # Calculate conversation
        calc_conv = ConversationHandler(
            entry_points=[CommandHandler("calculate", self.auth_middleware.wrap(self.trading.start_calculate))],
            states=TRADING_STATES,
            fallbacks=[CommandHandler("cancel", self.trading.cancel)],
            name="calculate",
            persistent=True,
        )
        app.add_handler(calc_conv)

        # Settings conversation
        settings_conv = ConversationHandler(
            entry_points=[CommandHandler("settings", self.auth_middleware.wrap(self.settings_handler.start))],
            states=SETTINGS_STATES,
            fallbacks=[CommandHandler("cancel", self.settings_handler.cancel)],
            name="settings",
            persistent=True,
        )
        app.add_handler(settings_conv)

        # Admin commands
        app.add_handler(CommandHandler("admin", self.auth_middleware.wrap_admin(self.admin.dashboard)))
        app.add_handler(CommandHandler("stats", self.auth_middleware.wrap_admin(self.admin.stats)))
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

    async def _handle_callback(self, update, context):
        """Route callback queries to appropriate handlers"""
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

    def _setup_commands(self):
        commands = [
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
        # set_my_commands is async in PTB v20 — schedule it as a post-init
        async def set_commands(app):
            await app.bot.set_my_commands(commands)
        self.application.post_init = set_commands

    async def start(self):
        """Start the bot and all services (runs inside asyncio event loop)"""
        logger.info("Starting FX Signal Copier Bot...")

        # MetaApi requires a running event loop — create it here
        self.mt5_manager = MT5ConnectionManager(self.db)
        await self.mt5_manager.start()

        # Now safe to init handlers that may reference mt5_manager
        self._init_handlers()

        # Start background tasks
        asyncio.create_task(self._background_tasks())

        # Run the bot
        if settings.USE_WEBHOOK:
            await self.application.run_webhook(
                listen="0.0.0.0",
                port=settings.PORT,
                url_path=settings.BOT_TOKEN,
                webhook_url=f"{settings.APP_URL}/{settings.BOT_TOKEN}",
            )
        else:
            await self.application.run_polling()

    async def _background_tasks(self):
        """Run periodic background tasks using asyncio instead of APScheduler"""
        async def run_every(coro_fn, seconds):
            while True:
                try:
                    await coro_fn()
                except Exception as e:
                    logger.error(f"Background task error: {e}")
                await asyncio.sleep(seconds)

        async def process_expired():
            from services.subscription import SubscriptionService
            sub_service = SubscriptionService(self.db)
            count = sub_service.process_expired()
            if count > 0:
                logger.info(f"Processed {count} expired subscriptions")

        async def collect_metrics():
            self.monitoring.collect_metrics()

        await asyncio.gather(
            run_every(self._check_connections, 300),   # every 5 min
            run_every(collect_metrics, 900),            # every 15 min
            run_every(process_expired, 86400),          # daily
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

    async def stop(self):
        """Stop the bot and cleanup"""
        logger.info("Stopping bot...")
        if self.mt5_manager:
            await self.mt5_manager.stop()
        self.db.close()
        logger.info("Bot stopped")