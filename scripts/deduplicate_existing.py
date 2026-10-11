import asyncio
from sqlalchemy import select
from app.db.session import async_session
from app.db.models import Gig
from app.utils.normalization import normalize_artist_name, normalize_venue_name

async def deduplicate_db():
    async with async_session() as session:
        result = await session.execute(select(Gig).order_by(Gig.id.asc()))
        all_gigs = result.scalars().all()

        seen = {}
        to_delete = []
        updated_count = 0

        for gig in all_gigs:
            norm_artist = normalize_artist_name(gig.artist)
            norm_venue = normalize_venue_name(gig.venue)
            key = (norm_artist, gig.gig_date, norm_venue)

            if key in seen:
                primary = seen[key]
                # Merge valuable info into primary record
                changed = False
                if not primary.ticket_cost and gig.ticket_cost:
                    primary.ticket_cost = gig.ticket_cost
                    changed = True
                if not primary.ticket_url and gig.ticket_url:
                    primary.ticket_url = gig.ticket_url
                    changed = True
                if not primary.lineup_details and gig.lineup_details:
                    primary.lineup_details = gig.lineup_details
                    changed = True
                if gig.relevance_score > primary.relevance_score:
                    primary.relevance_score = gig.relevance_score
                    primary.relevance_reason = gig.relevance_reason
                    changed = True

                if changed:
                    updated_count += 1

                to_delete.append(gig)
            else:
                seen[key] = gig

        print(f"Total gigs before: {len(all_gigs)}")
        print(f"Duplicates found to delete: {len(to_delete)}")
        print(f"Primary records merged/updated: {updated_count}")

        for dup in to_delete:
            await session.delete(dup)

        await session.commit()
        print(f"Deduplication complete. Total unique gigs remaining: {len(seen)}")

if __name__ == "__main__":
    asyncio.run(deduplicate_db())
