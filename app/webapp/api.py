import json
from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from app.db.session import get_db
from app.db.models import Gig, Subscriber
from app.config import settings

api_router = APIRouter(prefix="/api")

class SubscriberPreferencesUpdate(BaseModel):
    chat_id: str
    min_score: int = 40
    genres: List[str] = []
    locations: List[str] = ["Helsinki", "Espoo", "Vantaa"]
    notification_days: List[str] = ["fri"]
    is_active: bool = False # Deactivated by default

@api_router.get("/user-preferences/{chat_id}")
async def get_user_preferences(chat_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscriber).where(Subscriber.chat_id == chat_id))
    sub = result.scalars().first()
    if not sub:
        return {
            "chat_id": chat_id,
            "min_score": 40,
            "genres": [],
            "locations": ["Helsinki", "Espoo", "Vantaa"],
            "notification_days": ["fri"],
            "is_active": False
        }
    return sub.to_dict()

@api_router.post("/user-preferences")
async def save_user_preferences(payload: SubscriberPreferencesUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Subscriber).where(Subscriber.chat_id == payload.chat_id))
    sub = result.scalars().first()
    loc_json = json.dumps(payload.locations)
    days_json = json.dumps(payload.notification_days)
    genres_json = json.dumps(payload.genres)

    if not sub:
        sub = Subscriber(
            chat_id=payload.chat_id,
            min_score=payload.min_score,
            genres=genres_json,
            location=loc_json,
            notification_day=days_json,
            is_active=payload.is_active
        )
        db.add(sub)
    else:
        sub.min_score = payload.min_score
        sub.genres = genres_json
        sub.location = loc_json
        sub.notification_day = days_json
        sub.is_active = payload.is_active

    await db.commit()
    await db.refresh(sub)
    return {"status": "ok", "preferences": sub.to_dict()}

@api_router.get("/available-genres")
async def get_available_genres():
    """Returns the full list of selectable target genres including extended rock & metal."""
    return settings.TARGET_GENRES

from datetime import datetime, date

@api_router.get("/gigs")
async def get_gigs(
    genre: Optional[str] = None,
    genres: Optional[str] = None, # comma-separated list of genres e.g. "Doom Metal,Post-Punk"
    city: Optional[str] = None,
    min_score: int = Query(0, ge=0, le=100),
    max_score: Optional[int] = Query(None, ge=0, le=100),
    relevance_tier: Optional[str] = None, # 'all', 'high' (80+), 'medium' (50-79), 'low' (20-49)
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    venue: Optional[str] = None,
    include_past: bool = Query(False),
    sort_by: str = Query("date_asc", pattern="^(date_asc|date_desc|score_desc|score_asc)$"),
    db: AsyncSession = Depends(get_db)
):
    stmt = select(Gig).where(Gig.relevance_score >= min_score)

    # Filter out past events by default: only show gigs on or after today
    today_str = date.today().isoformat()
    if not include_past:
        effective_date_from = max(date_from, today_str) if date_from else today_str
        # Include events with specific dates >= today OR marked as 'Upcoming'
        stmt = stmt.where((Gig.gig_date >= effective_date_from) | (Gig.gig_date == "Upcoming"))
    elif date_from:
        stmt = stmt.where(Gig.gig_date >= date_from)

    if max_score is not None:
        stmt = stmt.where(Gig.relevance_score <= max_score)

    if relevance_tier:
        tier = relevance_tier.lower()
        if tier == "high":
            stmt = stmt.where(Gig.relevance_score >= 80)
        elif tier == "medium":
            stmt = stmt.where(Gig.relevance_score >= 50, Gig.relevance_score < 80)
        elif tier == "low":
            stmt = stmt.where(Gig.relevance_score >= 20, Gig.relevance_score < 50)

    if city:
        stmt = stmt.where(Gig.city.ilike(f"%{city}%"))
    if venue:
        stmt = stmt.where(Gig.venue.ilike(f"%{venue}%"))
    if date_to:
        stmt = stmt.where(Gig.gig_date <= date_to)

    # Sorting
    if sort_by == "score_desc":
        stmt = stmt.order_by(Gig.relevance_score.desc(), Gig.gig_date.asc())
    elif sort_by == "score_asc":
        stmt = stmt.order_by(Gig.relevance_score.asc(), Gig.gig_date.asc())
    elif sort_by == "date_desc":
        stmt = stmt.order_by(Gig.gig_date.desc(), Gig.relevance_score.desc())
    else:  # default date_asc
        stmt = stmt.order_by(Gig.gig_date.asc(), Gig.relevance_score.desc())

    result = await db.execute(stmt)
    gigs = result.scalars().all()

    # Multi-choice genre filtering
    selected_genres = []
    if genres:
        selected_genres.extend([g.strip().lower() for g in genres.split(",") if g.strip()])
    if genre:
        selected_genres.append(genre.strip().lower())

    if selected_genres:
        import re
        filtered_gigs = []
        for g in gigs:
            gig_genres = [item.lower() for item in g.get_genres_list()]
            match = False
            for sel in selected_genres:
                # Use word-boundary or clean matching to avoid false positives (e.g. 'pop' matching 'pop-punk')
                pattern = re.compile(rf"\b{re.escape(sel)}\b", re.IGNORECASE)
                if any(pattern.search(gg) or sel == gg for gg in gig_genres):
                    match = True
                    break
            if match:
                filtered_gigs.append(g)
        gigs = filtered_gigs

    return [g.to_dict() for g in gigs]

@api_router.post("/query-filter")
async def query_filter(payload: dict):
    from app.llm.query_parser import parse_user_query
    query_text = payload.get("query", "")
    filters = await parse_user_query(query_text)
    return filters.model_dump()

@api_router.get("/genres")
async def get_all_genres(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Gig.genres))
    all_genres = set()
    for row in result.scalars():
        if row:
            try:
                import json
                items = json.loads(row)
                for item in items:
                    all_genres.add(item.strip())
            except Exception:
                pass
    return sorted(list(all_genres))
