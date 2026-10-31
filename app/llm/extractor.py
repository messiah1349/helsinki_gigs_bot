import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.llm.client import call_gemini

logger = logging.getLogger(__name__)

class EventEnrichment(BaseModel):
    artist: str = Field(default="", description="Normalized main artist name or festival title")
    artist_country: Optional[str] = Field(None, description="Country of origin of artist if known (e.g. FI, US, UK, SE)")
    genres: List[str] = Field(default_factory=list, description="List of recognized genres")
    popularity_tier: str = Field("emerging_local", description="Tier within their genre: 'world_famous', 'established', or 'emerging_local'")
    relevance_score: int = Field(0, description="Relevance score from 0 to 100 based on user's target genres")
    relevance_reason: str = Field("", description="Concise explanation why it is or isn't relevant to user's taste")
    short_description: str = Field("", description="Short 1-2 sentence description of the musical style and band")
    lineup_details: Optional[str] = Field(None, description="Information on support bands, headliners, or festival details")
    is_festival: bool = Field(False, description="True if this is a music festival or multi-band fest")

SYSTEM_ENRICHMENT_PROMPT = """You are an expert music curator specializing in alternative, indie rock, punk, pop-punk, rock, metal, underground, and indie music scenes in Helsinki.

User Taste Profile (Highly relevant genres):
- Hardcore: Hardcore, Post-Hardcore, Screamo, Emo
- Punk: Punk, Pop-Punk, Post-Punk
- Metal: Progressive Metal, Post-Metal, Avantgarde Metal, Black Metal, Death Metal, Doom Metal, Sludge Metal, Heavy Metal, Thrash Metal, Power Metal, Gothic Metal, Symphonic Metal, Industrial Metal, Melodic Death Metal
- Rock / Alternative / Indie: Indie Rock, Progressive Rock, Art Rock, Post-Rock, Noise Rock, Math Rock, Stoner Rock, Psychedelic Rock, Alternative Rock, Grunge, Shoegaze, Darkwave
- Acoustic: Singer-Songwriters, Dark Folk, Acoustic

Popularity Tiers (Evaluate within the band's musical genre and scene):
1. "world_famous": Internationally renowned icons, global headliners within their genre, major arena/festival headliners (e.g. Bruce Dickinson, Ghost, Bring Me The Horizon, Turnstile, The Smile, Fontaines D.C., Sleep Token).
2. "established": Recognized national or international touring acts, scene veterans, established cult-following bands with multiple albums/tours (e.g. The Ocean, Terveet Kädet, Krallice, Huora, The Chats, Haken).
3. "emerging_local": Young local talents, up-and-coming indie/underground bands, local club openers, newer demo/EP acts.

Scoring criteria (relevance_score from 0 to 100):
- 80 - 100: Direct hit in user's core genres (e.g., Hardcore, Post-Hardcore, Screamo, Emo, Punk, Pop-Punk, Post-Punk, Post-Metal, Post-Rock, Doom, Progressive Metal, Avantgarde, Math Rock, Indie Rock, Shoegaze).
- 50 - 79: Adjacent or highly interesting alternative/indie/heavy genres (e.g., Psychedelic Rock, Stoner Rock, Heavy Metal, Thrash Metal, Folk, Dark Ambient, Industrial, Death Metal, Grunge, Hard Rock).
- 20 - 49: General pop-rock/classic rock but less aligned.
- 0 - 19: Completely non-relevant genres (e.g. mainstream Pop, Hip-Hop/Rap, Techno/Club DJ night, Stand-up comedy, sports, corporate events).

Output JSON schema strictly matching:
{
  "artist": "Normalized artist or event name",
  "artist_country": "Country code or name or null",
  "genres": ["Genre1", "Genre2"],
  "popularity_tier": "world_famous" | "established" | "emerging_local",
  "relevance_score": integer 0-100,
  "relevance_reason": "Concise reason why it fits or does not fit",
  "short_description": "Short 1-2 sentence summary of style",
  "lineup_details": "Support acts or null",
  "is_festival": boolean
}
"""

async def enrich_gig(raw_event: Dict[str, Any]) -> EventEnrichment:
    """
    Enriches a parsed gig using Gemini Flash via direct REST call.
    """
    user_prompt = (
        f"Analyze and enrich this gig:\n"
        f"Artist/Title: {raw_event.get('artist', '')}\n"
        f"Venue: {raw_event.get('venue', '')}\n"
        f"City: {raw_event.get('city', 'Helsinki')}\n"
        f"Date: {raw_event.get('gig_date', '')}\n"
        f"Info/Description: {raw_event.get('raw_description', '') or ''}"
    )

    try:
        raw_json_str = await call_gemini(
            prompt=user_prompt,
            system_instruction=SYSTEM_ENRICHMENT_PROMPT,
            json_response=True,
            temperature=0.2
        )
        data = json.loads(raw_json_str)
        return EventEnrichment(**data)
    except Exception as e:
        logger.error(f"Error enriching gig '{raw_event.get('artist')}': {e}")
        artist_name = raw_event.get("artist", "")
        return EventEnrichment(
            artist=artist_name,
            artist_country=raw_event.get("artist_country"),
            genres=["Live Music"],
            relevance_score=30,
            relevance_reason="Automatic fallback: LLM enrichment pending.",
            short_description=f"Live concert at {raw_event.get('venue')}",
            lineup_details=raw_event.get("lineup_details"),
            is_festival=raw_event.get("is_festival", False)
        )
