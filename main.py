import logging

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


if __name__ == '__main__':
    logger.info("Starting Tonpo Bot v1.0.0")
    from bot.main import Bot
    bot = Bot()
    bot.run()