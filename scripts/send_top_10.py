import asyncio
import os
import httpx
from dotenv import load_dotenv

from app.db.session import init_db, async_session
from app.db.models import Gig, Subscriber
from app.parsers.venues.tavastia import TavastiaParser
from app.parsers.venues.kuudes_linja import KuudesLinjaParser
from app.parsers.venues.aaniwalli import AaniwalliParser
from app.parsers.venues.rocks import OnTheRocksParser
from app.llm.extractor import enrich_gig
from app.bot.notifications import format_gig_message

load_dotenv(".env")

async def send_top_10_relevant():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = "46340594"  # From Eugene

    await init_db()

    print("Fetching events from primary venues (Tavastia, Kuudes Linja, Ääniwalli, On The Rocks)...")
    venues = [
        TavastiaParser(),
        KuudesLinjaParser(),
        AaniwalliParser(),
        OnTheRocksParser()
    ]

    all_raw = []
    for v in venues:
        try:
            evs = await v.parse()
            print(f"  • {v.name}: {len(evs)} events")
            all_raw.extend(evs)
        except Exception as e:
            print(f"  • {v.name} error: {e}")

    # Prioritize events containing keywords related to target genres to optimize batch LLM scoring
    genre_keywords = [
        "metal", "death", "black", "doom", "post", "prog", "rock", "hardcore",
        "screamo", "sludge", "noise", "math", "punk", "folk", "acoustic", "singer", "ambient"
    ]

    def candidate_score(ev):
        text = (ev.get("artist", "") + " " + ev.get("raw_description", "")).lower()
        return sum(1 for kw in genre_keywords if kw in text)

    # Sort candidates by keyword presence
    all_raw.sort(key=candidate_score, reverse=True)
    candidates = all_raw[:35]  # score top 35 candidates with Gemini Flash

    print(f"\nAnalyzing top {len(candidates)} prospective candidates with Gemini Flash...")
    enriched_gigs = []
    for i, raw in enumerate(candidates, 1):
        try:
            enrichment = await enrich_gig(raw)
            print(f"[{i}/{len(candidates)}] {enrichment.artist} -> Score: {enrichment.relevance_score}/100 | Genres: {enrichment.genres}")
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
        except Exception as e:
            print(f"Error enriching {raw.get('artist')}: {e}")

    async with async_session() as session:
        for gig in top_10:
            session.add(gig)
        await session.commit()
    print("Saved top 10 gigs to database.")

    print(f"\nSending TOP 10 highest relevance gigs to chat {chat_id}...")
    send_url = f"https://api.telegram.org/bot{token}/sendMessage"

    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(send_url, json={
            "chat_id": chat_id,
            "text": "🏆 <b>TOP 10 Upcoming Helsinki Gigs with Highest Relevance:</b>\n<i>(Scored & curated by Gemini Flash Latest)</i>",
            "parse_mode": "HTML"
        })

        for gig in top_10:
            text = format_gig_message(gig)
            await client.post(send_url, json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            })
            await asyncio.sleep(0.5)

    print("\n🎉 Sent top 10 highest relevance gigs successfully!")

if __name__ == "__main__":
    asyncio.run(send_top_10_relevant())
