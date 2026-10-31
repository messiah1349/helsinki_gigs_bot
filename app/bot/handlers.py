import logging
from aiogram import Router, F
from aiogram.types import (
    Message,
    CallbackQuery,
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
        "📱 <b>Open the Web App</b> (tap the button below or <b>🎸 Gigs App</b> in the bottom menu) to:\n"
        "  — Filter concerts by genres & popularity grades\n"
        "  — Pick dates using the visual calendar\n"
        "  — Configure your <b>🔔 Weekly Alerts</b>\n\n"
        "💬 <b>Ask in plain English or Finnish</b> anytime in this chat (e.g. <i>'any indie rock, punk or hardcore gigs next weekend?'</i>) and I will find them for you!"
    )
    await message.answer(
        welcome_text,
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

@router.message(Command("help"))
async def handle_help(message: Message):
    help_text = (
        "🔍 <b>Helsinki Gigs Bot Commands:</b>\n\n"
        "/start - Register & launch Gig Finder\n"
        "/alerts - View alert status, toggle on/off & edit preferences\n"
        "/help - Show this guide\n\n"
        "💡 <b>Tip:</b> You can write plain text in English or Finnish like:\n"
        "• <i>'show me math rock and screamo shows'</i>\n"
        "• <i>'what is playing at Tavastia or Kuudes Linja in November?'</i>\n"
        "• <i>'acoustic folk gigs under 25 euros'</i>"
    )
    await message.answer(help_text, reply_markup=get_main_keyboard(), parse_mode="HTML")

DAY_NAMES_MAP = {
    "mon": "Mon", "tue": "Tue", "wed": "Wed", "thu": "Thu", "fri": "Fri", "sat": "Sat", "sun": "Sun"
}

TIER_NAMES_MAP = {
    "world_famous": "🌍 World Famous",
    "established": "🔥 Established",
    "emerging_local": "🌱 Local & Rising"
}

def get_alerts_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "🔴 Deactivate Alerts" if is_active else "🟢 Activate Alerts"
    toggle_data = "alerts_toggle_off" if is_active else "alerts_toggle_on"
    alerts_url = f"{settings.WEBAPP_URL}?open=alerts"

    kb = [
        [
            InlineKeyboardButton(text=toggle_text, callback_data=toggle_data)
        ],
        [
            InlineKeyboardButton(
                text="⚙️ Alert Settings (Web App)",
                web_app=WebAppInfo(url=alerts_url)
            )
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def build_alerts_status_text(sub: Subscriber) -> str:
    status_emoji = "🟢 <b>ACTIVE</b>" if sub.is_active else "🔴 <b>DEACTIVATED</b>"
    
    # Days
    days = sub.get_notification_days_list()
    days_str = ", ".join(DAY_NAMES_MAP.get(d, d.upper()) for d in days) if days else "None"
    
    # Locations
    locs = sub.get_locations_list()
    locs_str = ", ".join(locs) if locs else "All"

    # Popularity
    tiers = sub.get_popularity_tiers_list()
    tiers_str = ", ".join(TIER_NAMES_MAP.get(t, t) for t in tiers) if tiers else "All"

    # Genres
    genres = sub.get_genres_list()
    genres_str = ", ".join(genres) if genres else "All genres"

    text = (
        f"🔔 <b>Gig Alerts Status:</b> {status_emoji}\n\n"
        f"📅 <b>Alert Days:</b> {days_str}\n"
        f"📍 <b>Locations:</b> {locs_str}\n"
        f"⭐ <b>Popularity:</b> {tiers_str}\n"
        f"🏷 <b>Genres:</b> {genres_str}\n\n"
        "<i>Use the buttons below to toggle alerts or open Settings to customize filters:</i>"
    )
    return text

@router.message(Command("alerts"))
async def handle_alerts(message: Message):
    chat_id = str(message.chat.id)
    async with async_session() as session:
        sub = (await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))).scalars().first()
        if not sub:
            sub = Subscriber(
                chat_id=chat_id,
                username=message.from_user.username if message.from_user else None,
                first_name=message.from_user.first_name if message.from_user else None,
                is_active=False
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)

        text = build_alerts_status_text(sub)
        kb = get_alerts_keyboard(sub.is_active)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

@router.callback_query(F.data.startswith("alerts_toggle_"))
async def handle_alerts_toggle(callback: CallbackQuery):
    chat_id = str(callback.message.chat.id)
    target_state = callback.data == "alerts_toggle_on"

    async with async_session() as session:
        sub = (await session.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))).scalars().first()
        if sub:
            sub.is_active = target_state
            await session.commit()
            await session.refresh(sub)

            text = build_alerts_status_text(sub)
            kb = get_alerts_keyboard(sub.is_active)
            try:
                await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            except Exception:
                pass

    status_word = "activated 🟢" if target_state else "deactivated 🔴"
    await callback.answer(f"Alerts {status_word}!")

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
