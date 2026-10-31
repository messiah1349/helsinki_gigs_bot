import asyncio
import logging
import sys
from app.db.session import init_db
from app.scheduler.jobs import run_parsers_and_enrich
from app.bot.bot import get_bot
from app.bot.notifications import send_new_gigs_notification

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("run_pipeline")

async def main():
    logger.info("Initializing database...")
    await init_db()

    logger.info("Executing gig parser and enrichment pipeline...")
    await run_parsers_and_enrich()

    bot = get_bot()
    if bot:
        logger.info("Checking and dispatching scheduled alerts to active subscribers...")
        try:
            from app.bot.notifications import dispatch_scheduled_alerts
            await dispatch_scheduled_alerts(bot)
        finally:
            await bot.session.close()

    logger.info("Pipeline execution complete.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"Pipeline failed with error: {e}")
        sys.exit(1)
