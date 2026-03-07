#!/usr/bin/env python3
"""
Main entry point for FX Signal Copier Bot
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings
from database.database import db_manager
from bot.main import Bot
from utils.logger import setup_logging

# Setup logging
logger = setup_logging(__name__)


def main():
    """Main entry point"""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    
    # Create bot instance
    bot = Bot()
    
    try:
        # Run bot
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        bot.stop()
        logger.info("Bot shutdown complete")


if __name__ == "__main__":
    main()