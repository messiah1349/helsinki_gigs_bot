import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.llm.client import call_gemini

logger = logging.getLogger(__name__)

class QueryFilters(BaseModel):
    genres: List[str] = Field(default_factory=list, description="Target genres mentioned (e.g., ['post-rock', 'doom metal'])")
    date_from: Optional[str] = Field(None, description="Start date in YYYY-MM-DD format if specified")
    date_to: Optional[str] = Field(None, description="End date in YYYY-MM-DD format if specified")
    city: Optional[str] = Field(None, description="City filter: Helsinki, Espoo, or Vantaa")
    min_score: Optional[int] = Field(None, description="Minimum relevance score threshold if implied (e.g. 50)")
    max_price: Optional[float] = Field(None, description="Max ticket cost in euros if mentioned")
    keyword: Optional[str] = Field(None, description="Specific band name, venue or keyword search")

NL_FILTER_PROMPT = """You are a smart query understanding agent for a Helsinki gig discovery bot.
Your job is to translate free-form natural language queries from users into structured filter criteria.

Target cities: Helsinki, Espoo, Vantaa.
Today's reference year is 2026.

Examples:
- "any post-punk or math rock gigs this weekend?" -> genres: ["post-punk", "math rock"], etc.
- "metal concerts in On the Rocks next month" -> genres: ["metal"], keyword: "On the Rocks"
- "cheap folk or acoustic shows under 20 euros" -> genres: ["folk", "acoustic"], max_price: 20

Output JSON schema strictly matching:
{
  "genres": ["genre1", "genre2"],
  "date_from": "YYYY-MM-DD or null",
  "date_to": "YYYY-MM-DD or null",
  "city": "Helsinki/Espoo/Vantaa or null",
  "min_score": integer or null,
  "max_price": float or null,
  "keyword": "string or null"
}
"""

async def parse_user_query(query_text: str) -> QueryFilters:
    """
    Parses a user text into structured gig search filters using Gemini Flash via direct REST call.
    """
    user_prompt = f"User query: {query_text}"

    try:
        raw_json_str = await call_gemini(
            prompt=user_prompt,
            system_instruction=NL_FILTER_PROMPT,
            json_response=True,
            temperature=0.1
        )
        data = json.loads(raw_json_str)
        return QueryFilters(**data)
    except Exception as e:
        logger.error(f"Error parsing user query '{query_text}': {e}")
        return QueryFilters(keyword=query_text)
