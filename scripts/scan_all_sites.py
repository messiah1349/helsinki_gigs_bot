import asyncio
import logging
import json
from sqlalchemy import select
from app.db.session import init_db, async_session
from app.db.models import Gig
from app.parsers.venues.tavastia import TavastiaParser
from app.parsers.venues.kuudes_linja import KuudesLinjaParser
from app.parsers.venues.aaniwalli import AaniwalliParser
from app.parsers.venues.rocks import OnTheRocksParser
from app.parsers.tiketti import TikettiParser
from app.llm.extractor import enrich_gig
from app.utils.normalization import normalize_artist_name, normalize_venue_name
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("scan_pipeline")

async def scan_and_update():
    await init_db()

    parsers = [
        TavastiaParser(),
        KuudesLinjaParser(),
        AaniwalliParser(),
        OnTheRocksParser(),
        TikettiParser()
    ]

    all_raw_events = []
    logger.info("Starting comprehensive scan across venues and aggregators...")
    for p in parsers:
        try:
            events = await p.parse()
            logger.info(f"Parsed {len(events)} events from {p.name}")
            all_raw_events.extend(events)
        except Exception as e:
            logger.error(f"Parser {p.name} failed: {e}")

    logger.info(f"Total parsed raw events: {len(all_raw_events)}")

    async with async_session() as session:
        # Load existing gigs to detect matches and re-enrich if necessary
        res = await session.execute(select(Gig))
        existing_gigs = res.scalars().all()

        gig_index = {}
        url_index = {}
        for g in existing_gigs:
            norm_key = (normalize_artist_name(g.artist), g.gig_date, normalize_venue_name(g.venue))
            gig_index[norm_key] = g
            if g.source_url:
                url_index[g.source_url] = g

        new_count = 0
        updated_count = 0
        re_enriched_count = 0

        # Also re-enrich any existing gig that has generic or fallback tags
        for g in existing_gigs:
            current_genres = g.get_genres_list()
            artist_low = g.artist.lower()
            # If current genres contains generic Live Music or indie/rock bands that might benefit from Indie Rock scoring
            if any(term in artist_low for term in ["indie", "rock", "wolf", "eyes", "mountain", "goats", "razorlight", "tams", "younghearted", "dinah", "dina", "kissa", "death hawks", "lala salama"]) or "Live Music" in current_genres:
                raw_dummy = {
                    "artist": g.artist,
                    "venue": g.venue,
                    "city": g.city,
                    "gig_date": g.gig_date,
                    "raw_description": g.short_description or "",
                    "lineup_details": g.lineup_details,
                    "is_festival": g.is_festival
                }
                enrichment = await enrich_gig(raw_dummy)
                g.artist_country = enrichment.artist_country or g.artist_country
                g.genres = json.dumps(enrichment.genres)
                g.relevance_score = enrichment.relevance_score
                g.relevance_reason = enrichment.relevance_reason
                g.short_description = enrichment.short_description
                re_enriched_count += 1
                await session.commit()

        logger.info(f"Re-enriched {re_enriched_count} prospective indie & rock records.")

        # Now process raw events
        for i, raw in enumerate(all_raw_events, 1):
            source_url = raw.get("source_url")
            raw_artist = raw.get("artist", "").strip()
            gig_date = raw.get("gig_date", "").strip()
            raw_venue = raw.get("venue", "").strip()

            if not raw_artist or not gig_date:
                continue

            norm_key = (normalize_artist_name(raw_artist), gig_date, normalize_venue_name(raw_venue))
            existing = url_index.get(source_url) or gig_index.get(norm_key)

            if existing:
                # Merge fresh details
                changed = False
                if not existing.ticket_cost and raw.get("ticket_cost"):
                    existing.ticket_cost = raw.get("ticket_cost")
                    changed = True
                if not existing.ticket_url and raw.get("ticket_url"):
                    existing.ticket_url = raw.get("ticket_url")
                    changed = True
                if raw.get("lineup_details") and not existing.lineup_details:
                    existing.lineup_details = raw.get("lineup_details")
                    changed = True
                if changed:
                    updated_count += 1
                    await session.commit()
                continue

            # New gig -> enrich with Gemini Flash
            enrichment = await enrich_gig(raw)
            new_gig = Gig(
                artist=enrichment.artist or raw_artist,
                artist_country=enrichment.artist_country or raw.get("artist_country"),
                genres=json.dumps(enrichment.genres),
                gig_date=gig_date,
                venue=raw_venue,
                city=raw.get("city", "Helsinki"),
                ticket_cost=raw.get("ticket_cost"),
                ticket_url=raw.get("ticket_url"),
                source_url=source_url,
                short_description=enrichment.short_description,
                relevance_reason=enrichment.relevance_reason,
                relevance_score=enrichment.relevance_score,
                lineup_details=enrichment.lineup_details or raw.get("lineup_details"),
                is_festival=enrichment.is_festival or raw.get("is_festival", False),
                is_enriched=True,
                is_notified=False
            )
            session.add(new_gig)
            await session.commit()
            await session.refresh(new_gig)

            gig_index[norm_key] = new_gig
            if source_url:
                url_index[source_url] = new_gig
            new_count += 1

        logger.info(f"Scan complete! Added {new_count} new gigs, updated {updated_count} existing records.")

if __name__ == "__main__":
    asyncio.run(scan_and_update())
