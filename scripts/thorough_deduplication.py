import asyncio
import re
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Gig
from app.utils.normalization import normalize_artist_name, normalize_venue_name, extract_tiketti_event_id

async def thorough_deduplication():
    async with async_session() as session:
        result = await session.execute(select(Gig).order_by(Gig.id.asc()))
        all_gigs = result.scalars().all()

        # Step 1: Remove seed dummy test gigs (IDs 1 to 10 with dummy source_urls)
        deleted_count = 0
        cleaned_list = []
        for g in all_gigs:
            if g.source_url and ("#haken" in g.source_url or "#hlb" in g.source_url or "#banned" in g.source_url or "#pagan" in g.source_url or "#formypain" in g.source_url or "#moonshot" in g.source_url or "#dazedolls" in g.source_url or "#ndm" in g.source_url):
                await session.delete(g)
                deleted_count += 1
            else:
                cleaned_list.append(g)

        print(f"Removed {deleted_count} seed placeholder records.")
        await session.commit()

        # Step 2: Merge and deduplicate by:
        # A) Shared Tiketti event ID (e.g. 118788 for Haken)
        # B) (normalized_artist, gig_date, normalized_venue)
        # C) (normalized_artist, normalized_venue) where one is 'Upcoming' and other has real date

        tiketti_id_map = {}
        exact_map = {}
        fuzzy_map = {} # (normalized_artist, normalized_venue)

        to_remove = []
        merged_count = 0

        for g in cleaned_list:
            if g in to_remove:
                continue

            tid = extract_tiketti_event_id(g.source_url) or extract_tiketti_event_id(g.ticket_url)
            na = normalize_artist_name(g.artist)
            nv = normalize_venue_name(g.venue)
            exact_key = (na, g.gig_date, nv)
            fuzzy_key = (na, nv)

            primary = None

            # Check 1: Shared Tiketti ID
            if tid and tid in tiketti_id_map:
                primary = tiketti_id_map[tid]
            # Check 2: Exact artist + date + venue
            elif exact_key in exact_map:
                primary = exact_map[exact_key]
            # Check 3: Same artist and venue, where one is 'Upcoming' or both dates match closely
            elif fuzzy_key in fuzzy_map:
                candidate = fuzzy_map[fuzzy_key]
                # If one date is 'Upcoming' and the other is a specific date, merge into the specific date!
                if (g.gig_date == "Upcoming" or candidate.gig_date == "Upcoming") or (g.gig_date == candidate.gig_date):
                    primary = candidate

            if primary and primary != g:
                # Merge details into primary
                if primary.gig_date == "Upcoming" and g.gig_date != "Upcoming":
                    primary.gig_date = g.gig_date
                if not primary.ticket_cost and g.ticket_cost:
                    primary.ticket_cost = g.ticket_cost
                if not primary.ticket_url and g.ticket_url:
                    primary.ticket_url = g.ticket_url
                if not primary.lineup_details and g.lineup_details:
                    primary.lineup_details = g.lineup_details
                if g.relevance_score > primary.relevance_score:
                    primary.relevance_score = g.relevance_score
                    primary.relevance_reason = g.relevance_reason

                to_remove.append(g)
                merged_count += 1
            else:
                if tid:
                    tiketti_id_map[tid] = g
                exact_map[exact_key] = g
                fuzzy_map[fuzzy_key] = g

        print(f"Total duplicates to remove: {len(to_remove)}")
        for dup in to_remove:
            await session.delete(dup)

        await session.commit()
        print(f"Thorough deduplication complete! Merged {merged_count} duplicate events.")

if __name__ == "__main__":
    asyncio.run(thorough_deduplication())
