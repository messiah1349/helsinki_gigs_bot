import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from app.parsers.base import BaseParser

class TavastiaParser(BaseParser):
    def __init__(self, include_semifinal: bool = True):
        self.include_semifinal = include_semifinal

    @property
    def name(self) -> str:
        return "Tavastia & Semifinal"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        urls = [("Tavastia-klubi", "https://tavastiaklubi.fi/")]
        if self.include_semifinal:
            urls.append(("Semifinal", "https://tavastiaklubi.fi/semifinal/"))

        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            for venue_name, url in urls:
                try:
                    resp = await client.get(url)
                    if resp.status_code != 200:
                        continue
                    
                    soup = BeautifulSoup(resp.text, "html.parser")
                    tables = soup.find_all("table", class_="event-table")
                    
                    for table in tables:
                        rows = table.find_all("tr")
                        for row in rows:
                            # Day name, year, date
                            date_div = row.find("div", class_="date")
                            year_div = row.find("div", class_="year")
                            if not date_div:
                                continue

                            date_text = date_div.get_text(strip=True)  # e.g. "8.10."
                            year_text = year_div.get_text(strip=True) if year_div else "2026"
                            
                            # Normalize date to YYYY-MM-DD
                            try:
                                day, month = date_text.rstrip(".").split(".")
                                gig_date = f"{year_text}-{int(month):02d}-{int(day):02d}"
                            except Exception:
                                gig_date = f"{date_text}{year_text}"

                            items = row.find_all("a", class_="item")
                            for item in items:
                                title_div = item.find("div", class_="title")
                                if not title_div:
                                    continue
                                artist_title = title_div.get_text(strip=True)
                                event_url = item.get("href", "")
                                
                                # Ticket price
                                tickets_div = item.find("div", class_="tickets")
                                ticket_cost = None
                                if tickets_div:
                                    ticket_cost = " ".join(tickets_div.get_text().split())
                                elif item.find("span", class_="status-sold_out"):
                                    ticket_cost = "Sold out"

                                is_fest = "fest" in artist_title.lower() or "festival" in artist_title.lower()

                                results.append({
                                    "artist": artist_title,
                                    "gig_date": gig_date,
                                    "venue": venue_name,
                                    "city": "Helsinki",
                                    "ticket_cost": ticket_cost,
                                    "ticket_url": event_url,
                                    "source_url": event_url or f"{url}#{artist_title}_{gig_date}",
                                    "raw_description": f"Live at {venue_name}: {artist_title}",
                                    "lineup_details": artist_title if ("," in artist_title or "+" in artist_title) else None,
                                    "is_festival": is_fest
                                })
                except Exception as e:
                    print(f"Error parsing {venue_name}: {e}")

        return results
