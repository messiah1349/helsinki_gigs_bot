from datetime import datetime
import logging
from typing import List
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Gig, Subscriber
from app.config import settings

logger = logging.getLogger(__name__)

def format_gig_message(gig: Gig) -> str:
    genres = ", ".join(gig.get_genres_list()) or "Rock/Metal"
    country_badge = f" ({gig.artist_country})" if gig.artist_country else ""
    price_info = f"💶 <b>Tickets:</b> {gig.ticket_cost}\n" if gig.ticket_cost else ""
    lineup_info = f"👥 <b>Lineup / Support:</b> {gig.lineup_details}\n" if gig.lineup_details else ""
    
    msg = (
        f"🎸 <b>{gig.artist}</b>{country_badge}\n"
        f"📅 <b>Date:</b> {gig.gig_date}\n"
        f"📍 <b>Venue:</b> {gig.venue} ({gig.city})\n"
        f"🏷 <b>Genres:</b> {genres}\n"
        f"🔥 <b>Relevance:</b> {gig.relevance_score}/100\n"
        f"{price_info}"
        f"{lineup_info}"
        f"📝 <b>Why it matches:</b> {gig.relevance_reason or gig.short_description}\n"
    )
    if gig.ticket_url or gig.source_url:
        link = gig.ticket_url or gig.source_url
        msg += f"🔗 <a href='{link}'>Tickets & Info</a>\n"

    return msg

def matches_subscriber_preferences(gig: Gig, sub: Subscriber, current_weekday: str) -> bool:
    """
    Checks whether a gig matches a subscriber's personal preferences:
    - Notification days: does user prefer notifications on current_weekday? (multi-choice list)
    - Relevance score threshold: gig.relevance_score >= sub.min_score
    - Locations: Helsinki, Espoo, Vantaa (multi-choice list)
    - Genres: if user selected specific genres, check if gig has overlapping genre tags
    """
    # 1. Multi-choice days of week check
    sub_days = [d.lower() for d in sub.get_notification_days_list()]
    if "any" not in sub_days and current_weekday.lower() not in sub_days:
        return False

    # 2. Score check
    if gig.relevance_score < (sub.min_score or 40):
        return False

    # 3. Multi-choice locations check (Helsinki, Espoo, Vantaa)
    sub_locs = [loc.lower() for loc in sub.get_locations_list()]
    gig_city = (gig.city or "Helsinki").lower()
    if not any(loc in gig_city for loc in sub_locs):
        return False

    # 4. Genre check (if subscriber customized their genres list)
    sub_genres = sub.get_genres_list()
    if sub_genres:
        gig_genres = [g.lower() for g in gig.get_genres_list()]
        has_genre_match = any(
            any(sg.lower() in gg or gg in sg.lower() for gg in gig_genres)
            for sg in sub_genres
        )
        if not has_genre_match:
            return False

    return True

async def send_new_gigs_notification(bot: Bot, gigs: List[Gig]):
    if not gigs:
        return

    # Map current weekday: mon, tue, wed, thu, fri, sat, sun
    days_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    current_weekday = days_map[datetime.utcnow().weekday()]

    async with async_session() as session:
        subscribers = (await session.execute(select(Subscriber).where(Subscriber.is_active == True))).scalars().all()
        
        if not subscribers and settings.TELEGRAM_CHANNEL_ID:
            subscribers = [Subscriber(chat_id=settings.TELEGRAM_CHANNEL_ID, min_score=settings.MIN_RELEVANCE_SCORE)]

        for gig in gigs:
            text = format_gig_message(gig)
            for sub in subscribers:
                if not sub.is_active:
                    continue

                if matches_subscriber_preferences(gig, sub, current_weekday):
                    try:
                        await bot.send_message(
                            chat_id=sub.chat_id,
                            text=text,
                            parse_mode="HTML",
                            disable_web_page_preview=True
                        )
                        sub.last_notified_at = datetime.utcnow()
                    except TelegramForbiddenError as e:
                        # User blocked or deleted the bot: deactivate them immediately
                        logger.warning(f"User {sub.chat_id} blocked or deleted bot. Deactivating subscription.")
                        sub.is_active = False
                        await session.commit()
                    except TelegramBadRequest as e:
                        # Chat not found or deleted account
                        if "chat not found" in str(e).lower() or "user not found" in str(e).lower():
                            logger.warning(f"Chat {sub.chat_id} not found. Deactivating subscription.")
                            sub.is_active = False
                            await session.commit()
                        else:
                            logger.error(f"Telegram BadRequest for {sub.chat_id}: {e}")
                    except Exception as e:
                        logger.error(f"Failed to send gig #{gig.id} to {sub.chat_id}: {e}")

            # Mark gig as notified in db
            gig.is_notified = True
            await session.commit()
