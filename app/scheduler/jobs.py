import json
import logging
from typing import List, Dict, Any
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Gig
from app.parsers.venues.tavastia import TavastiaParser
from app.parsers.venues.kuudes_linja import KuudesLinjaParser
from app.parsers.venues.aaniwalli import AaniwalliParser
from app.parsers.venues.rocks import OnTheRocksParser
from app.parsers.livenation import LiveNationParser
from app.parsers.tiketti import TikettiParser
from app.llm.extractor import enrich_gig
from app.config import settings
from app.utils.normalization import normalize_artist_name, normalize_venue_name, extract_tiketti_event_id

logger = logging.getLogger(__name__)

async def run_parsers_and_enrich() -> List[Gig]:
    """
    Two-phase ingestion pipeline enforcing strict source priority:
    - Phase 1 (PRIMARY): Scrapes dedicated venue websites (Tavastia, Semifinal, Kuudes Linja, Ääniwalli, On The Rocks).
      Events are saved or updated directly from the venue official source.
    - Phase 2 (SECONDARY): Scrapes aggregators (Tiketti).
      If an event from an aggregator matches an existing venue event (by Tiketti event ID, artist+venue, or artist+date),
      it ONLY supplements missing fields (like missing ticket price) without overriding venue data or creating duplicates.
      Only genuinely new gigs not featured in venue parsers are added.
    """
    venue_parsers = [
        TavastiaParser(),
        KuudesLinjaParser(),
        AaniwalliParser(),
        OnTheRocksParser()
    ]
    aggregator_parsers = [
        LiveNationParser(),
        TikettiParser()
    ]

    # 1. Fetch Venue Events (Priority 1)
    venue_events: List[Dict[str, Any]] = []
    for vp in venue_parsers:
        logger.info(f"[Priority 1 - Venue] Running parser: {vp.name}")
        try:
            evs = await vp.parse()
            logger.info(f"Parsed {len(evs)} events from {vp.name}")
            venue_events.extend(evs)
        except Exception as e:
            logger.error(f"Venue parser {vp.name} failed: {e}")

    # 2. Fetch Aggregator Events (Priority 2 - Secondary)
    aggregator_events: List[Dict[str, Any]] = []
    for ap in aggregator_parsers:
        logger.info(f"[Priority 2 - Aggregator] Running parser: {ap.name}")
        try:
            evs = await ap.parse()
            logger.info(f"Parsed {len(evs)} events from {ap.name}")
            aggregator_events.extend(evs)
        except Exception as e:
            logger.error(f"Aggregator parser {ap.name} failed: {e}")

    new_relevant_gigs: List[Gig] = []

    async with async_session() as session:
        # Load all existing gigs for smart deduplication & updating
        existing_gigs_stmt = select(Gig)
        existing_gigs = (await session.execute(existing_gigs_stmt)).scalars().all()

        # Build indexes:
        tiketti_id_index = {}
        gig_index = {}
        fuzzy_index = {}
        url_index = {}

        def index_gig(g: Gig):
            norm_key = (normalize_artist_name(g.artist), g.gig_date, normalize_venue_name(g.venue))
            fuzzy_key = (normalize_artist_name(g.artist), normalize_venue_name(g.venue))
            tid = extract_tiketti_event_id(g.source_url) or extract_tiketti_event_id(g.ticket_url)
            gig_index[norm_key] = g
            fuzzy_index[fuzzy_key] = g
            if tid:
                tiketti_id_index[tid] = g
            if g.source_url:
                url_index[g.source_url] = g

        for g in existing_gigs:
            index_gig(g)

        # Helper to find match
        def find_match(raw_event: Dict[str, Any]):
            source_url = raw_event.get("source_url")
            raw_artist = raw_event.get("artist", "").strip()
            gig_date = raw_event.get("gig_date", "").strip()
            raw_venue = raw_event.get("venue", "").strip()

            na = normalize_artist_name(raw_artist)
            nv = normalize_venue_name(raw_venue)
            norm_key = (na, gig_date, nv)
            fuzzy_key = (na, nv)
            raw_tid = extract_tiketti_event_id(source_url) or extract_tiketti_event_id(raw_event.get("ticket_url"))

            if raw_tid and raw_tid in tiketti_id_index:
                return tiketti_id_index[raw_tid]
            if source_url and source_url in url_index:
                return url_index[source_url]
            if norm_key in gig_index:
                return gig_index[norm_key]
            if fuzzy_key in fuzzy_index:
                cand = fuzzy_index[fuzzy_key]
                if cand.gig_date == "Upcoming" or gig_date == "Upcoming" or cand.gig_date == gig_date:
                    return cand
            return None

        # Process Phase 1: Venue Events (Primary authority)
        for raw in venue_events:
            raw_artist = raw.get("artist", "").strip()
            gig_date = raw.get("gig_date", "").strip()
            raw_venue = raw.get("venue", "").strip()
            source_url = raw.get("source_url")

            if not raw_artist or not gig_date:
                continue

            existing = find_match(raw)
            if existing:
                # Update with authoritative venue details
                updated = False
                if raw_venue and existing.venue != raw_venue:
                    existing.venue = raw_venue
                    updated = True
                if gig_date != "Upcoming" and existing.gig_date != gig_date:
                    existing.gig_date = gig_date
                    updated = True
                if raw.get("ticket_cost") and not existing.ticket_cost:
                    existing.ticket_cost = raw.get("ticket_cost")
                    updated = True
                if raw.get("lineup_details") and not existing.lineup_details:
                    existing.lineup_details = raw.get("lineup_details")
                    updated = True
                if updated:
                    await session.commit()
                continue

            # Brand new venue gig
            logger.info(f"[Venue Ingestion] Enriching: {raw_artist} ({gig_date} at {raw_venue})")
            enrichment = await enrich_gig(raw)
            gig = Gig(
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
                popularity_tier=getattr(enrichment, "popularity_tier", "emerging_local") or "emerging_local",
                lineup_details=enrichment.lineup_details or raw.get("lineup_details"),
                is_festival=enrichment.is_festival or raw.get("is_festival", False),
                is_enriched=True,
                is_notified=False
            )
            session.add(gig)
            await session.commit()
            await session.refresh(gig)
            index_gig(gig)

            if gig.relevance_score >= settings.MIN_RELEVANCE_SCORE:
                new_relevant_gigs.append(gig)

        # Process Phase 2: Aggregator Events (Secondary - Supplement only)
        for raw in aggregator_events:
            raw_artist = raw.get("artist", "").strip()
            gig_date = raw.get("gig_date", "").strip()
            raw_venue = raw.get("venue", "").strip()
            source_url = raw.get("source_url")

            if not raw_artist or not gig_date:
                continue

            existing = find_match(raw)
            if existing:
                # Event already discovered from venue: ONLY supplement missing metadata
                updated = False
                if not existing.ticket_cost and raw.get("ticket_cost"):
                    existing.ticket_cost = raw.get("ticket_cost")
                    updated = True
                if not existing.ticket_url and raw.get("ticket_url"):
                    existing.ticket_url = raw.get("ticket_url")
                    updated = True
                if updated:
                    await session.commit()
                continue

            # Gig does not exist on venue website (e.g. from smaller venue/hall covered only by Tiketti)
            logger.info(f"[Aggregator Ingestion] New event not found on venues: {raw_artist} ({gig_date} at {raw_venue})")
            enrichment = await enrich_gig(raw)
            gig = Gig(
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
                popularity_tier=getattr(enrichment, "popularity_tier", "emerging_local") or "emerging_local",
                lineup_details=enrichment.lineup_details or raw.get("lineup_details"),
                is_festival=enrichment.is_festival or raw.get("is_festival", False),
                is_enriched=True,
                is_notified=False
            )
            session.add(gig)
            await session.commit()
            await session.refresh(gig)
            index_gig(gig)

            if gig.relevance_score >= settings.MIN_RELEVANCE_SCORE:
                new_relevant_gigs.append(gig)

    logger.info(f"Pipeline finished. Found {len(new_relevant_gigs)} new relevant gigs.")
    return new_relevant_gigs
