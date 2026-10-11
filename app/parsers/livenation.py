import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from app.parsers.base import BaseParser

class LiveNationParser(BaseParser):
    @property
    def name(self) -> str:
        return "Live Nation Finland"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        base_url = "https://www.livenation.fi"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}

        async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
            try:
                # 1. Fetch frontpage to get all active tour/artist slugs (-tickets-adp)
                resp = await client.get(base_url)
                if resp.status_code != 200:
                    return results

                artist_paths = set(re.findall(r'href="(/[a-zA-Z0-9\-_%]+-tickets-adp\d+)"', resp.text))

                # 2. Inspect each artist page
                for path in artist_paths:
                    artist_url = f"{base_url}{path}"
                    try:
                        a_resp = await client.get(artist_url)
                        if a_resp.status_code != 200:
                            continue

                        # Extract artist name from title
                        # e.g. "Placebo Liput, Kiertueet ja Keikkapäivät..."
                        title_m = re.search(r"<title>(.*?)</title>", a_resp.text)
                        raw_title = title_m.group(1) if title_m else ""
                        artist_name = raw_title.split(" Liput")[0].split(" Tickets")[0].strip()
                        if not artist_name:
                            continue

                        # Parse events listed on the artist page
                        # Matches: <time dateTime="2026-10-18T00:00:00.000Z"...>...<h3...>(Helsinki Venue)</h3>
                        events_found = re.finditer(
                            r'<time[^>]*dateTime="([0-9]{4}-[0-9]{2}-[0-9]{2})[^\"]*"[^>]*>.*?<h3[^>]*>(.*?)</h3>',
                            a_resp.text,
                            re.DOTALL
                        )

                        for ev in events_found:
                            gig_date = ev.group(1)
                            location_str = re.sub(r"<[^>]+>", " ", ev.group(2)).strip()
                            
                            # Filter for Helsinki, Espoo, Vantaa
                            low_loc = location_str.lower()
                            city = "Helsinki"
                            if "helsinki" in low_loc:
                                city = "Helsinki"
                            elif "espoo" in low_loc:
                                city = "Espoo"
                            elif "vantaa" in low_loc:
                                city = "Vantaa"
                            else:
                                continue # Skip concerts outside capital area (e.g. Tampere, Turku)

                            # Clean venue name
                            venue = location_str
                            for c in ["Helsinki", "Espoo", "Vantaa"]:
                                venue = re.sub(rf"(?i)\b{c}\b", "", venue).strip()
                            venue = venue or "Helsinki Venue"

                            results.append({
                                "artist": artist_name,
                                "gig_date": gig_date,
                                "venue": venue,
                                "city": city,
                                "ticket_cost": None,
                                "ticket_url": artist_url,
                                "source_url": f"{artist_url}#{gig_date}",
                                "raw_description": f"Live Nation Finland presents {artist_name} at {venue}, {city}.",
                                "lineup_details": None,
                                "is_festival": False
                            })
                    except Exception as e:
                        continue

            except Exception as e:
                print(f"Error parsing Live Nation: {e}")

        return results
