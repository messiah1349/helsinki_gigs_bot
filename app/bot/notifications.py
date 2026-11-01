from datetime import datetime, date
import logging
from typing import List, Optional
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from sqlalchemy import select, and_
from app.db.session import async_session
from app.db.models import Gig, Subscriber, SubscriberNotifiedGig
from app.config import settings

logger = logging.getLogger(__name__)

TIER_BADGES = {
    "world_famous": "🌍 World Famous",
    "established": "🔥 Established Act",
    "emerging_local": "🌱 Local & Rising"
}

def get_gig_ticket_keyboard(gig: Gig) -> Optional[InlineKeyboardMarkup]:
    ticket_url = gig.ticket_url or gig.source_url
    if not ticket_url:
        return None
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎟 Get Tickets & Info", url=ticket_url)]
    ])

def get_alert_management_keyboard() -> InlineKeyboardMarkup:
    alerts_url = f"{settings.WEBAPP_URL}?open=alerts"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔴 Deactivate Alerts", callback_data="alerts_toggle_off"),
            InlineKeyboardButton(text="⚙️ Alert Settings", web_app=WebAppInfo(url=alerts_url))
        ]
    ])

def format_gig_message(gig: Gig) -> str:
    genres = ", ".join(gig.get_genres_list()) or "Rock/Metal"
    country_badge = f" ({gig.artist_country})" if gig.artist_country else ""
    tier_label = TIER_BADGES.get(gig.popularity_tier, "🌱 Local & Rising")
    price_info = f"💶 <b>Tickets:</b> {gig.ticket_cost}\n" if gig.ticket_cost else ""
    lineup_info = f"👥 <b>Lineup / Support:</b> {gig.lineup_details}\n" if gig.lineup_details else ""
    fest_info = "🎪 <b>Festival / Special Event</b>\n" if gig.is_festival else ""

    msg = (
        f"🎸 <b>{gig.artist}</b>{country_badge}\n"
        f"📅 <b>Date:</b> {gig.gig_date}\n"
        f"📍 <b>Venue:</b> {gig.venue} ({gig.city})\n"
        f"🏷 <b>Genres:</b> {genres}\n"
        f"⭐ <b>Popularity:</b> {tier_label}\n"
        f"{fest_info}"
        f"{price_info}"
        f"{lineup_info}"
        f"📝 <b>Info:</b> {gig.relevance_reason or gig.short_description}\n"
    )
    return msg

def matches_subscriber_preferences(gig: Gig, sub: Subscriber, current_weekday: str) -> bool:
    """
    Checks whether a gig matches a subscriber's personal preferences:
    - Notification days: does user prefer notifications on current_weekday? (multi-choice list)
    - Popularity tier: is gig.popularity_tier in sub's allowed tiers?
    - Locations: Helsinki, Espoo, Vantaa (multi-choice list)
    - Genres: if user selected specific genres, check if gig has overlapping genre tags
    """
    # 1. Multi-choice days of week check
    sub_days = [d.lower() for d in sub.get_notification_days_list()]
    if current_weekday.lower() != "any" and "any" not in sub_days and current_weekday.lower() not in sub_days:
        return False

    # 2. Popularity tier check
    sub_tiers = [t.lower() for t in sub.get_popularity_tiers_list()]
    gig_tier = (gig.popularity_tier or "emerging_local").lower()
    if gig_tier not in sub_tiers:
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

async def dispatch_scheduled_alerts(bot: Bot):
    """
    Runs during scheduled runs (e.g. 7 PM daily).
    Checks all active subscribers:
    - If today is one of subscriber's notification days:
      finds all upcoming gigs matching user preferences that this specific subscriber
      has NOT yet received, sends them, and records them in subscriber_notified_gigs.
    """
    # Day mapping (Helsinki timezone)
    days_map = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    current_weekday = days_map[datetime.now().weekday()]
    today_str = date.today().isoformat()

    logger.info(f"Dispatching scheduled alerts for weekday: {current_weekday.upper()}...")

    async with async_session() as session:
        subscribers = (await session.execute(
            select(Subscriber).where(Subscriber.is_active == True)
        )).scalars().all()

        if not subscribers:
            logger.info("No active subscribers found.")
            return

        # Fetch all future gigs
        upcoming_gigs = (await session.execute(
            select(Gig).where((Gig.gig_date >= today_str) | (Gig.gig_date == "Upcoming")).order_by(Gig.gig_date.asc())
        )).scalars().all()

        for sub in subscribers:
            # Check if subscriber wants alerts today
            sub_days = [d.lower() for d in sub.get_notification_days_list()]
            if "any" not in sub_days and current_weekday not in sub_days:
                continue

            # Load gigs already sent to this subscriber
            sent_ids = set((await session.execute(
                select(SubscriberNotifiedGig.gig_id).where(SubscriberNotifiedGig.subscriber_chat_id == sub.chat_id)
            )).scalars().all())

            # Filter matching gigs not yet received by this user
            matching_gigs = []
            for gig in upcoming_gigs:
                if gig.id in sent_ids:
                    continue
                if matches_subscriber_preferences(gig, sub, current_weekday):
                    matching_gigs.append(gig)

            if not matching_gigs:
                logger.info(f"Subscriber {sub.chat_id}: no new matching gigs today.")
                continue

            logger.info(f"Sending {len(matching_gigs)} new gigs to subscriber {sub.chat_id}...")

            # Format human dates for header
            today_formatted = date.today().strftime("%d.%m.%Y")
            if sub.last_notified_at:
                since_formatted = sub.last_notified_at.strftime("%d.%m.%Y")
            else:
                # Default to last 7 days if first notification
                from datetime import timedelta
                since_formatted = (date.today() - timedelta(days=7)).strftime("%d.%m.%Y")

            # Send single introductory announcement message
            intro_text = (
                f"📣 <b>New gig announcements ({since_formatted} – {today_formatted}):</b>\n\n"
                f"Found <b>{len(matching_gigs)}</b> new show(s) matching your taste profile:"
            )
            try:
                await bot.send_message(
                    chat_id=sub.chat_id,
                    text=intro_text,
                    parse_mode="HTML"
                )
            except TelegramForbiddenError:
                logger.warning(f"User {sub.chat_id} blocked bot. Deactivating.")
                sub.is_active = False
                await session.commit()
                continue
            except Exception as e:
                logger.error(f"Failed to send intro to {sub.chat_id}: {e}")

            sent_count = 0
            for gig in matching_gigs:
                text = format_gig_message(gig)
                kb = get_gig_ticket_keyboard(gig)

                try:
                    await bot.send_message(
                        chat_id=sub.chat_id,
                        text=text,
                        reply_markup=kb,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    # Record that user received this gig
                    session.add(SubscriberNotifiedGig(subscriber_chat_id=sub.chat_id, gig_id=gig.id))
                    sub.last_notified_at = datetime.utcnow()
                    await session.commit()
                    sent_count += 1
                except TelegramForbiddenError:
                    logger.warning(f"User {sub.chat_id} blocked bot. Deactivating.")
                    sub.is_active = False
                    await session.commit()
                    break
                except TelegramBadRequest as e:
                    if "chat not found" in str(e).lower() or "user not found" in str(e).lower():
                        logger.warning(f"Chat {sub.chat_id} not found. Deactivating.")
                        sub.is_active = False
                        await session.commit()
                        break
                    else:
                        logger.error(f"Telegram BadRequest for {sub.chat_id}: {e}")
                except Exception as e:
                    logger.error(f"Failed to send gig #{gig.id} to {sub.chat_id}: {e}")

            # Send alert summary & settings controls only at the very end of the batch
            if sent_count > 0:
                summary_text = (
                    f"✅ <i>That's all {sent_count} new matching gig(s) for today!</i>\n"
                    "Manage your subscription or customize preferences below:"
                )
                try:
                    await bot.send_message(
                        chat_id=sub.chat_id,
                        text=summary_text,
                        reply_markup=get_alert_management_keyboard(),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    logger.error(f"Failed to send alert summary to {sub.chat_id}: {e}")

async def send_new_gigs_notification(bot: Bot, gigs: List[Gig]):
    """Compatibility wrapper that calls dispatch_scheduled_alerts."""
    await dispatch_scheduled_alerts(bot)
