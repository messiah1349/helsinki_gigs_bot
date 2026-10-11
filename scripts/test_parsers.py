import asyncio
from app.parsers.venues.tavastia import TavastiaParser
from app.parsers.venues.kuudes_linja import KuudesLinjaParser
from app.parsers.venues.aaniwalli import AaniwalliParser
from app.parsers.venues.rocks import OnTheRocksParser
from app.parsers.tiketti import TikettiParser

async def test_parsers():
    parsers = [
        TavastiaParser(),
        KuudesLinjaParser(),
        AaniwalliParser(),
        OnTheRocksParser(),
        TikettiParser()
    ]
    for p in parsers:
        print(f"\n--- Testing {p.name} ---")
        try:
            events = await p.parse()
            print(f"Total events parsed: {len(events)}")
            if events:
                sample = events[0]
                print(f"Sample: Artist: '{sample['artist']}', Date: '{sample['gig_date']}', Venue: '{sample['venue']}', Price: '{sample.get('ticket_cost')}'")
        except Exception as e:
            print(f"Error in {p.name}: {e}")

if __name__ == "__main__":
    asyncio.run(test_parsers())
