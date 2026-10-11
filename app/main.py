import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.db.session import init_db
from app.webapp.api import api_router
from app.bot.bot import get_bot, get_dispatcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("helsinki_gigs")

scheduler = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler

    # 1. Initialize DB tables
    logger.info("Initializing database...")
    await init_db()

    # 2. Telegram Bot initialization
    bot = get_bot()
    dp = get_dispatcher()
    bot_task = None

    if bot:
        try:
            from aiogram.types import MenuButtonCommands
            await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
            logger.info("Configured Telegram command Menu Button.")
        except Exception as e:
            logger.warning(f"Failed to set chat menu button: {e}")

    if bot:
        logger.info("Starting Telegram Bot long-polling...")
        bot_task = asyncio.create_task(dp.start_polling(bot))

    # 3. Optional internal scheduler (Default: False, recommended via cron for low RAM)
    if settings.ENABLE_INTERNAL_SCHEDULER:
        try:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            from app.scheduler.jobs import run_parsers_and_enrich
            from app.bot.notifications import send_new_gigs_notification

            async def scheduled_pipeline_job():
                logger.info("Executing scheduled gig parser and enrichment pipeline...")
                new_gigs = await run_parsers_and_enrich()
                if bot and new_gigs:
                    logger.info(f"Broadcasting {len(new_gigs)} new gigs to subscribers...")
                    await send_new_gigs_notification(bot, new_gigs)

            scheduler = AsyncIOScheduler()
            logger.info(f"Setting up internal scheduler: days={settings.CRON_SCHEDULE_DAYS}, hour={settings.CRON_SCHEDULE_HOUR}")
            scheduler.add_job(
                scheduled_pipeline_job,
                trigger="cron",
                day_of_week=settings.CRON_SCHEDULE_DAYS,
                hour=settings.CRON_SCHEDULE_HOUR,
                minute=settings.CRON_SCHEDULE_MINUTE
            )
            scheduler.start()
        except Exception as e:
            logger.error(f"Failed to start internal scheduler: {e}")
    else:
        logger.info("Internal scheduler disabled. Using external cron runner (app.scheduler.run_pipeline).")

    yield

    # Shutdown
    if bot_task:
        bot_task.cancel()
    if scheduler and scheduler.running:
        scheduler.shutdown()
    if bot:
        await bot.session.close()

app = FastAPI(title="Helsinki Gigs Tracker", lifespan=lifespan)

# Include REST API
app.include_router(api_router)

# Mount Static directory
app.mount("/static", StaticFiles(directory="app/webapp/static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse("app/webapp/static/index.html")

@app.post("/api/admin/run-pipeline")
async def trigger_pipeline_now():
    """Manual trigger endpoint to run parser & notification pipeline in an isolated background subprocess."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "app.scheduler.run_pipeline"
    )
    return {"status": "ok", "message": f"Pipeline started in background subprocess (PID: {proc.pid})"}
