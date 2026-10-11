import json
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, Float
from app.db.session import Base

class Gig(Base):
    __tablename__ = "gigs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Artist & Event Information
    artist = Column(String(255), nullable=False, index=True)
    artist_country = Column(String(100), nullable=True) # e.g. "US", "Finland", etc.
    genres = Column(Text, nullable=True)                 # JSON string list of genres
    
    # Date & Venue
    gig_date = Column(String(50), nullable=False, index=True)  # YYYY-MM-DD or formatted
    venue = Column(String(255), nullable=False, index=True)
    city = Column(String(100), nullable=False, default="Helsinki")
    
    # Financials & Event details
    ticket_cost = Column(String(100), nullable=True)
    ticket_url = Column(String(500), nullable=True)
    source_url = Column(String(500), nullable=True, unique=True)
    
    # Descriptions & Relevance
    short_description = Column(Text, nullable=True)
    relevance_reason = Column(Text, nullable=True)
    relevance_score = Column(Integer, default=0, index=True)  # 0 to 100
    
    # Lineup / Festival info
    # e.g., festival name or "Support for X", "Headliner: Y, Support: Z"
    lineup_details = Column(Text, nullable=True)
    is_festival = Column(Boolean, default=False)

    # Tracking & State
    is_enriched = Column(Boolean, default=False)
    is_notified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    def get_genres_list(self):
        if not self.genres:
            return []
        try:
            return json.loads(self.genres)
        except Exception:
            return [g.strip() for g in self.genres.split(",") if g.strip()]

    def to_dict(self):
        return {
            "id": self.id,
            "artist": self.artist,
            "artist_country": self.artist_country,
            "genres": self.get_genres_list(),
            "gig_date": self.gig_date,
            "venue": self.venue,
            "city": self.city,
            "ticket_cost": self.ticket_cost,
            "ticket_url": self.ticket_url,
            "source_url": self.source_url,
            "short_description": self.short_description,
            "relevance_reason": self.relevance_reason,
            "relevance_score": self.relevance_score,
            "lineup_details": self.lineup_details,
            "is_festival": self.is_festival,
            "is_notified": self.is_notified,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }


class Subscriber(Base):
    __tablename__ = "subscribers"

    id = Column(Integer, primary_key=True)
    chat_id = Column(String(100), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    first_name = Column(String(100), nullable=True)
    
    # Personalized Notification & Default Filter Preferences
    min_score = Column(Integer, default=40)
    genres = Column(Text, nullable=True)            # JSON list of chosen genres e.g. ["Doom Metal", "Post-Punk"]
    location = Column(String(50), default="all")    # "all", "helsinki", "suburbia"
    notification_day = Column(String(20), default="fri") # "mon", "tue", "wed", "thu", "fri", "sat", "sun", or "any"
    
    is_active = Column(Boolean, default=False)  # Alerts deactivated by default for new users
    last_notified_at = Column(DateTime, nullable=True)
    subscribed_at = Column(DateTime, default=datetime.utcnow)

    def get_genres_list(self):
        if not self.genres:
            return []
        try:
            return json.loads(self.genres)
        except Exception:
            return [g.strip() for g in self.genres.split(",") if g.strip()]

    def get_locations_list(self):
        if not self.location:
            return ["Helsinki", "Espoo", "Vantaa"]
        try:
            return json.loads(self.location)
        except Exception:
            return [self.location] if self.location != "all" else ["Helsinki", "Espoo", "Vantaa"]

    def get_notification_days_list(self):
        if not self.notification_day:
            return ["fri"]
        try:
            return json.loads(self.notification_day)
        except Exception:
            return [self.notification_day]

    def to_dict(self):
        return {
            "chat_id": self.chat_id,
            "username": self.username,
            "first_name": self.first_name,
            "min_score": self.min_score,
            "genres": self.get_genres_list(),
            "locations": self.get_locations_list(),
            "notification_days": self.get_notification_days_list(),
            "is_active": self.is_active
        }
