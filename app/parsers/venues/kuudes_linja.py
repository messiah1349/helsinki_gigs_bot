import re
import httpx
from bs4 import BeautifulSoup
from typing import List, Dict, Any
from app.parsers.base import BaseParser

class KuudesLinjaParser(BaseParser):
    @property
    def name(self) -> str:
        return "Kuudes Linja"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        url = "https://kuudeslinja.com/"

        # Month mapping for Finnish dates
        fi_months = {
            "tammikuuta": "01", "helmikuuta": "02", "maaliskuuta": "03", "huhtikuuta": "04",
            "toukokuuta": "05", "kesäkuuta": "06", "heinäkuuta": "07", "elokuuta": "08",
            "syyskuuta": "09", "lokakuuta": "10", "marraskuuta": "11", "joulukuuta": "12"
        }

        async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return results

                soup = BeautifulSoup(resp.text, "html.parser")
                events = soup.find_all("article", class_="event")

                for ev in events:
                    pvm_div = ev.find("div", class_="pvm")
                    title_div = ev.find("div", class_="title")
                    if not title_div or not pvm_div:
                        continue

                    title = title_div.get_text(strip=True)
                    pvm = pvm_div.get_text(strip=True)  # e.g. "Maanantai 5.10." or "Perjantai 29.1.2027"

                    # Parse date
                    date_match = re.search(r"(\d{1,2})\.(\d{1,2})\.?(?:(\d{4}))?", pvm)
                    gig_date = pvm
                    if date_match:
                        day = int(date_match.group(1))
                        month = int(date_match.group(2))
                        year = date_match.group(3) if date_match.group(3) else "2026"
                        gig_date = f"{year}-{month:02d}-{day:02d}"

                    # Info / price
                    info_div = ev.find("div", class_="info")
                    info_text = info_div.get_text(" ", strip=True) if info_div else ""
                    
                    price_match = re.search(r"(\d+[\d,\.]*\s*€(?:[^\n\r<]*))", info_text)
                    ticket_cost = price_match.group(1).strip() if price_match else None
                    if "loppuunmyyty" in title.lower() or "loppuunmyyty" in info_text.lower():
                        ticket_cost = "Loppuunmyyty / Sold out"

                    # Ticket link
                    ticket_btn = ev.find("a", href=re.compile(r"tiketti\.fi|eventu\.al|lippu\.fi|tickettailor"))
                    ticket_url = ticket_btn.get("href") if ticket_btn else None

                    # FB event or permalink
                    fb_btn = ev.find("a", href=re.compile(r"facebook\.com/events"))
                    source_url = ticket_url or (fb_btn.get("href") if fb_btn else f"https://kuudeslinja.com/#{title[:30]}_{gig_date}")

                    is_fest = "festival" in title.lower() or "fest" in title.lower() or "karnevaali" in title.lower()

                    results.append({
                        "artist": title,
                        "gig_date": gig_date,
                        "venue": "Kuudes Linja",
                        "city": "Helsinki",
                        "ticket_cost": ticket_cost,
                        "ticket_url": ticket_url,
                        "source_url": source_url,
                        "raw_description": f"{title}\n{info_text}",
                        "lineup_details": info_text,
                        "is_festival": is_fest
                    })
            except Exception as e:
                print(f"Error parsing Kuudes Linja: {e}")

        return results
