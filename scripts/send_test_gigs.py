import asyncio
import os
import random
import httpx
from dotenv import load_dotenv

from app.db.session import init_db, async_session
from app.db.models import Gig, Subscriber
from app.parsers.venues.tavastia import TavastiaParser
from app.parsers.venues.kuudes_linja import KuudesLinjaParser
from app.parsers.venues.aaniwalli import AaniwalliParser
from app.parsers.venues.rocks import OnTheRocksParser
from app.parsers.tiketti import TikettiParser
from app.llm.extractor import enrich_gig
from app.bot.notifications import format_gig_message
from app.config import settings

load_dotenv(".env")

async def get_or_wait_for_chat_id(token: str) -> str:
    # 1. Check if configured in .env
    env_chat = os.getenv("TELEGRAM_CHANNEL_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if env_chat:
        return env_chat

    # 2. Check DB subscribers
    async with async_session() as session:
        from sqlalchemy import select
        sub = (await session.execute(select(Subscriber))).scalars().first()
        if sub:
            return sub.chat_id

    # 3. Poll Telegram getUpdates
    print("\n[!] No chat_id or subscriber found in database or .env.")
    print("👉 Please open your bot in Telegram (@otec_cherysheva_bot) and press START (or send any message).")
    print("Waiting for your message...")
    
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    async with httpx.AsyncClient(timeout=15.0) as client:
        for _ in range(60): # wait up to 120 seconds
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get("result", [])
                    if results:
                        last_msg = results[-1].get("message") or results[-1].get("channel_post")
                        if last_msg:
                            chat_id = str(last_msg["chat"]["id"])
                            print(f"\n✅ Found chat from user: {chat_id}")
                            return chat_id
            except httpx.RequestError as exc:
                pass
            await asyncio.sleep(2)

    raise RuntimeError("Timed out waiting for message to @otec_cherysheva_bot")

async def send_10_random_events():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN is missing!")
        return

    await init_db()
    chat_id = await get_or_wait_for_chat_id(token)

    # 1. Gather events from venues and Tiketti
    print("\nFetching events from Helsinki venues...")
    parsers = [
        TavastiaParser(),
        KuudesLinjaParser(),
        AaniwalliParser(),
        OnTheRocksParser(),
        TikettiParser()
    ]

    all_raw = []
    for p in parsers:
        try:
            evs = await p.parse()
            print(f"  • {p.name}: {len(evs)} events")
            all_raw.extend(evs)
        except Exception as e:
            print(f"  • {p.name} failed: {e}")

    if not all_raw:
        print("No events found!")
        return

    # 2. Select 10 random events
    sample_size = min(10, len(all_raw))
    selected_raw = random.sample(all_raw, sample_size)
    print(f"\nSelected {sample_size} random events to enrich with Gemini Flash...")

    enriched_gigs = []
    for i, raw in enumerate(selected_raw, 1):
        print(f"[{i}/{sample_size}] Analyzing: '{raw.get('artist')}' at {raw.get('venue')}...")
        enrichment = await enrich_gig(raw)
        
        import json
        gig = Gig(
            artist=enrichment.artist or raw.get("artist"),
            artist_country=enrichment.artist_country or raw.get("artist_country"),
            genres=json.dumps(enrichment.genres),
            gig_date=raw.get("gig_date", "Upcoming"),
            venue=raw.get("venue", "Helsinki Venue"),
            city=raw.get("city", "Helsinki"),
            ticket_cost=raw.get("ticket_cost"),
            ticket_url=raw.get("ticket_url"),
            source_url=raw.get("source_url"),
            short_description=enrichment.short_description,
            relevance_reason=enrichment.relevance_reason,
            relevance_score=enrichment.relevance_score,
            lineup_details=enrichment.lineup_details or raw.get("lineup_details"),
            is_festival=enrichment.is_festival or raw.get("is_festival", False)
        )
        enriched_gigs.append(gig)

    # 3. Send to Telegram
    print(f"\nSending {len(enriched_gigs)} events to chat {chat_id}...")
    send_url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # Send intro header
        await client.post(send_url, json={
            "chat_id": chat_id,
            "text": "🎸 <b>[Test Run] Here are 10 upcoming Helsinki gigs enriched with Gemini Flash:</b>",
            "parse_mode": "HTML"
        })

        for gig in enriched_gigs:
            text = format_gig_message(gig)
            resp = await client.post(send_url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })
            if resp.status_code != 200:
                print(f"Error sending message: {resp.text}")
            await asyncio.sleep(0.5)

    print("\n🎉 Done! All 10 test gigs sent to the bot.")

if __name__ == "__main__":
    asyncio.run(send_10_random_events())
