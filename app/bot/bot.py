from aiogram import Bot, Dispatcher
from app.config import settings
from app.bot.handlers import router

bot: Bot = None
dp: Dispatcher = None

def get_bot() -> Bot:
    global bot
    if bot is None and settings.TELEGRAM_BOT_TOKEN:
        bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    return bot

def get_dispatcher() -> Dispatcher:
    global dp
    if dp is None:
        dp = Dispatcher()
        dp.include_router(router)
    return dp
