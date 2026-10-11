import re
import httpx
from typing import List, Dict, Any
from app.parsers.base import BaseParser
class TikettiParser(BaseParser):
    def __init__(self, target_cities: list = None):
        self.target_cities = target_cities or ["helsinki", "espoo", "vantaa"]

    @property
    def name(self) -> str:
        return "Tiketti Aggregator"

    async def parse(self) -> List[Dict[str, Any]]:
        results = []
        base_url = "https://www.tiketti.fi"
        search_page_url = f"{base_url}/tapahtumat"

        target_cities = [c.lower() for c in self.target_cities]

        async with httpx.AsyncClient(timeout=25.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
            try:
                # 1. Fetch search page to find data_md5
                page_resp = await client.get(search_page_url)
                if page_resp.status_code != 200:
                    return results

                md5_match = re.search(r'data_md5\s*=\s*"([^"]+)"', page_resp.text)
                if not md5_match:
                    return results

                data_md5 = md5_match.group(1)
                data_url = f"{base_url}/tapahtumat/d/{data_md5}"

                # 2. Fetch full JSON event data
                json_resp = await client.get(data_url)
                if json_resp.status_code != 200:
                    return results

                payload = json_resp.json()
                keys = payload.get("keys", [])
                events = payload.get("events", [])
                locations = payload.get("locations", {})

                # Find key indices
                idx_name = keys.index("name") if "name" in keys else 2
                idx_price = keys.index("priceinfo") if "priceinfo" in keys else 4
                idx_start = keys.index("start_date") if "start_date" in keys else 8
                idx_loc = keys.index("locationID") if "locationID" in keys else 10
                idx_texts = keys.index("texts") if "texts" in keys else 13
                idx_url = keys.index("url") if "url" in keys else 15
                idx_tags = keys.index("tags") if "tags" in keys else 14

                for ev in events:
                    loc_id = str(ev[idx_loc])
                    loc_obj = locations.get(loc_id, {})
                    city = loc_obj.get("city", "")

                    if not city or city.lower() not in target_cities:
                        continue

                    event_name = ev[idx_name]
                    # Filter out vouchers / gift cards / sports
                    lower_name = event_name.lower()
                    if any(bad in lower_name for bad in ["lahjakortti", "gift card", "voucher", "seagulls", "jokerit", "hifk", "ottelu"]):
                        continue

                    gig_date = ev[idx_start]
                    venue_name = loc_obj.get("name", "Unknown Venue")
                    ticket_cost = ev[idx_price] if ev[idx_price] else None
                    sub_url = ev[idx_url]
                    full_url = f"{base_url}{sub_url}" if sub_url.startswith("/") else sub_url
                    raw_texts = ev[idx_texts] if len(ev) > idx_texts else ""

                    is_fest = "fest" in lower_name or "festival" in lower_name

                    results.append({
                        "artist": event_name,
                        "gig_date": gig_date,
                        "venue": venue_name,
                        "city": city,
                        "ticket_cost": ticket_cost,
                        "ticket_url": full_url,
                        "source_url": full_url,
                        "raw_description": f"{event_name} at {venue_name}, {city}.\n{raw_texts[:300]}",
                        "lineup_details": event_name if ("," in event_name or "+" in event_name or "with" in lower_name) else None,
                        "is_festival": is_fest
                    })

            except Exception as e:
                print(f"Error parsing Tiketti: {e}")

        return results
