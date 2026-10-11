import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from app.parsers.base import BaseParser

class AaniwalliParser(BaseParser):
    @property
    def name(self) -> str:
        return "Ääniwalli"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        url = "https://aaniwalli.fi/events"

        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return results

                soup = BeautifulSoup(resp.text, "html.parser")
                event_wrappers = soup.find_all("div", class_="event-wrapper")

                for wrap in event_wrappers:
                    event_link = wrap.find("a", class_="event")
                    if not event_link:
                        continue

                    title_h1 = event_link.find("h1", class_="event-title")
                    title = title_h1.get_text(strip=True) if title_h1 else ""
                    if not title:
                        continue

                    # Path contains date: /events/2026-10-05-we_jazz_presents_wolf_eyes_us
                    href = event_link.get("href", "")
                    date_match = re.search(r"/events/(\d{4}-\d{2}-\d{2})", href)
                    gig_date = date_match.group(1) if date_match else ""

                    # Ticket link
                    buy_btn = wrap.find("a", class_="buy-button")
                    ticket_url = buy_btn.get("href") if buy_btn else None

                    # Source URL
                    source_url = f"https://aaniwalli.fi{href}" if href.startswith("/") else href

                    # Country code tag (e.g., (US), (UK))
                    country_span = event_link.find("span", class_="country-code")
                    country = country_span.get_text(strip=True).replace("(", "").replace(")", "") if country_span else None

                    is_fest = "fest" in title.lower() or "festival" in title.lower()

                    results.append({
                        "artist": title,
                        "gig_date": gig_date,
                        "venue": "Ääniwalli",
                        "city": "Helsinki",
                        "ticket_cost": None,
                        "ticket_url": ticket_url,
                        "source_url": source_url or ticket_url,
                        "raw_description": f"Event at Ääniwalli: {title}",
                        "lineup_details": title if ("&" in title or "+" in title or "supports" in title.lower()) else None,
                        "artist_country": country,
                        "is_festival": is_fest
                    })
            except Exception as e:
                print(f"Error parsing Ääniwalli: {e}")

        return results
