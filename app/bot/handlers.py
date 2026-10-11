import logging
from aiogram import Router, F
from aiogram.types import (
    Message,
    WebAppInfo,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ChatMemberUpdated
)
from aiogram.filters import CommandStart, Command, ChatMemberUpdatedFilter, KICKED, LEFT, MEMBER
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Subscriber, Gig
from app.bot.notifications import format_gig_message
from app.config import settings

logger = logging.getLogger(__name__)
router = Router()

def get_main_keyboard() -> InlineKeyboardMarkup:
    webapp_url = settings.WEBAPP_URL
    kb = [
        [
            InlineKeyboardButton(
                text="🎸 Open Gig Finder (Web App)",
                web_app=WebAppInfo(url=webapp_url)
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_persistent_reply_keyboard() -> ReplyKeyboardMarkup:
    webapp_url = settings.WEBAPP_URL
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎸 Open Gig Finder", web_app=WebAppInfo(url=webapp_url))]
        ],
        resize_keyboard=True,
        persistent=True
    )

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=KICKED | LEFT))
async def handle_user_blocked_bot(event: ChatMemberUpdated):
    """
    Triggered instantly when a user blocks or stops/deletes the bot.
    Immediately marks the user as inactive so no future alerts are sent.
    """
    chat_id = str(event.chat.id)
    logger.info(f"User {chat_id} blocked or deleted bot. Setting is_active=False.")
    async with async_session() as session:
        sub = (await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))).scalars().first()
        if sub:
            sub.is_active = False
            await session.commit()

@router.my_chat_member(ChatMemberUpdatedFilter(member_status_changed=MEMBER))
async def handle_user_unblocked_bot(event: ChatMemberUpdated):
    """
    Triggered if user unblocks or re-opens the bot.
    """
    chat_id = str(event.chat.id)
    logger.info(f"User {chat_id} returned to the bot.")

@router.message(CommandStart())
async def handle_start(message: Message):
    chat_id = str(message.chat.id)
    username = message.from_user.username if message.from_user else None
    first_name = message.from_user.first_name if message.from_user else None

    async with async_session() as session:
        sub = (await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))).scalars().first()
        if not sub:
            sub = Subscriber(
                chat_id=chat_id,
                username=username,
                first_name=first_name,
                min_score=settings.MIN_RELEVANCE_SCORE,
                is_active=False # Alerts deactivated by default for new users
            )
            session.add(sub)
            await session.commit()

    welcome_text = (
        f"👋 <b>Tervetuloa, {first_name or 'fellow music fan'}!</b>\n\n"
        "I track and aggregate upcoming live music across the capital area (<b>Helsinki, Espoo, Vantaa</b>).\n\n"
        "🎯 <b>Covered Genres:</b>\n"
        "• Hardcore: Hardcore, Post-Hardcore, Screamo, Emo\n"
        "• Punk: Punk, Pop-Punk, Post-Punk\n"
        "• Metal: Progressive, Post-Metal, Avantgarde, Doom, Black, Death, Sludge, Heavy/Thrash\n"
        "• Rock & Underground: Indie Rock, Post-Rock, Math Rock, Grunge, Shoegaze, Darkwave\n"
        "• Acoustic: Singer-Songwriters, Folk, Dark Ambient\n\n"
        "✨ <b>What you can do:</b>\n"
        "📱 <b>Open the Web App</b> (tap <b>🎸 Gigs App</b> in bottom menu or button below) to:\n"
        "  — Filter by multiple genres & locations\n"
        "  — Select exact date ranges using calendar buttons\n"
        "  — Adjust minimum relevance match % with a live slider\n"
        "  — Set your custom <b>🔔 Weekly Alert Days & Preferences</b>\n\n"
        "💬 <b>Ask in plain English or Finnish</b> anytime in this chat (e.g. <i>'any indie rock, punk or hardcore gigs next weekend?'</i>) and I will find them for you!"
    )
    await message.answer(
        welcome_text,
        reply_markup=get_persistent_reply_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("help"))
async def handle_help(message: Message):
    help_text = (
        "🔍 <b>Helsinki Gigs Bot Commands:</b>\n\n"
        "/start - Register for updates & open web app\n"
        "/gigs - List top upcoming relevant gigs\n"
        "/help - Show this guide\n\n"
        "💡 <b>Tip:</b> You can write plain text in English or Finnish like:\n"
        "• <i>'show me math rock and screamo shows'</i>\n"
        "• <i>'what is playing at Tavastia or Kuudes Linja in November?'</i>\n"
        "• <i>'acoustic folk gigs under 25 euros'</i>"
    )
    await message.answer(help_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

@router.message(Command("gigs"))
async def handle_gigs(message: Message):
    async with async_session() as session:
        query = select(Gig).where(Gig.relevance_score >= settings.MIN_RELEVANCE_SCORE).order_by(Gig.gig_date.asc()).limit(5)
        gigs = (await session.execute(query)).scalars().all()

        if not gigs:
            await message.answer("No upcoming gigs found matching your taste profile yet. Run parser update!")
            return

        for gig in gigs:
            await message.answer(format_gig_message(gig), parse_mode="HTML", disable_web_page_preview=True)

@router.message(F.text)
async def handle_natural_language_query(message: Message):
    from app.llm.query_parser import parse_user_query

    query_text = message.text.strip()
    await message.answer("🔍 <i>Searching matching gigs...</i>", parse_mode="HTML")

    filters = await parse_user_query(query_text)

    async with async_session() as session:
        stmt = select(Gig)

        # Relevance threshold
        min_score = filters.min_score or settings.MIN_RELEVANCE_SCORE
        stmt = stmt.where(Gig.relevance_score >= min_score)

        if filters.city:
            stmt = stmt.where(Gig.city.ilike(f"%{filters.city}%"))

        if filters.date_from:
            stmt = stmt.where(Gig.gig_date >= filters.date_from)
        if filters.date_to:
            stmt = stmt.where(Gig.gig_date <= filters.date_to)

        if filters.keyword:
            stmt = stmt.where(
                (Gig.artist.ilike(f"%{filters.keyword}%")) |
                (Gig.venue.ilike(f"%{filters.keyword}%")) |
                (Gig.short_description.ilike(f"%{filters.keyword}%"))
            )

        stmt = stmt.order_by(Gig.gig_date.asc()).limit(8)
        results = (await session.execute(stmt)).scalars().all()

        # In-memory genre filter matching
        if filters.genres:
            genres_lower = [g.lower() for g in filters.genres]
            matched = []
            for gig in results:
                gig_genres = [g.lower() for g in gig.get_genres_list()]
                if any(any(target in g for target in genres_lower) for g in gig_genres) or any(target in gig.artist.lower() for target in genres_lower):
                    matched.append(gig)
            if matched:
                results = matched

        if not results:
            await message.answer(
                f"No matching gigs found for: <b>{query_text}</b>.\nTry broadening your criteria or use the Web App.",
                reply_markup=get_main_keyboard(),
                parse_mode="HTML"
            )
            return

        await message.answer(f"🎯 Found {len(results)} matching gig(s):", parse_mode="HTML")
        for gig in results:
            await message.answer(format_gig_message(gig), parse_mode="HTML", disable_web_page_preview=True)
