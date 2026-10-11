import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from app.parsers.base import BaseParser

class OnTheRocksParser(BaseParser):
    @property
    def name(self) -> str:
        return "On The Rocks"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        # On The Rocks has /tapahtumat/ with loop-item articles
        url = "https://www.rocks.fi/tapahtumat/"

        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return results

                soup = BeautifulSoup(resp.text, "html.parser")
                articles = soup.find_all("article", class_="tapahtuma")

                for art in articles:
                    link_el = art.find("a", class_="img-link") or art.find("a", href=re.compile(r"/tapahtumat/"))
                    if not link_el:
                        continue

                    title = link_el.get("title", "") or link_el.get_text(strip=True)
                    event_url = link_el.get("href", "")
                    
                    # Check classes for genre hints (e.g. tapahtumaluokka-metal)
                    classes = art.get("class", [])
                    genre_hints = [c.replace("tapahtumaluokka-", "") for c in classes if c.startswith("tapahtumaluokka-")]

                    # Date or ticket info
                    ticket_div = art.find("div", class_="ticket-info")
                    ticket_cost = ticket_div.get_text(" ", strip=True) if ticket_div else None

                    tiketti_btn = art.find("a", class_="btn-tiketti")
                    ticket_url = tiketti_btn.get("href") if tiketti_btn else None

                    # If date not in card, we will extract or derive it, or let LLM parse from article slug / page
                    date_match = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", event_url)
                    gig_date = date_match.group(1).replace("/", "-") if date_match else ""

                    is_cancelled = "peruttu" in title.lower() or "canceled" in title.lower()
                    if is_cancelled:
                        continue  # skip cancelled events

                    is_fest = "fest" in title.lower() or "festival" in title.lower()

                    results.append({
                        "artist": title,
                        "gig_date": gig_date or "Upcoming",
                        "venue": "On The Rocks",
                        "city": "Helsinki",
                        "ticket_cost": ticket_cost,
                        "ticket_url": ticket_url or event_url,
                        "source_url": event_url,
                        "raw_description": f"Genre tags: {', '.join(genre_hints)}. {title}",
                        "lineup_details": title if ("," in title or "+" in title) else None,
                        "is_festival": is_fest
                    })
            except Exception as e:
                print(f"Error parsing On The Rocks: {e}")

        return results
