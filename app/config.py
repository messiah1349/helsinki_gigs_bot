import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

class Settings(BaseSettings):
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHANNEL_ID: str = ""  # Optional: broadcast to channel or subscribers

    # Web App URL
    WEBAPP_URL: str = "http://localhost:8000"

    # LLM Settings
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = "gemini-flash-latest"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/helsinki_gigs.db"

    # Parser & Notification Schedule
    # If False, run externally via system crontab to keep server memory minimal
    ENABLE_INTERNAL_SCHEDULER: bool = False
    CRON_SCHEDULE_DAYS: str = "wed,sun"
    CRON_SCHEDULE_HOUR: int = 10
    CRON_SCHEDULE_MINUTE: int = 0

    # Target Regions & Cities
    REGIONS: List[str] = ["Helsinki", "Espoo", "Vantaa"]

    # Target Genres for reference & settings
    TARGET_GENRES: List[str] = [
        # Hardcore group
        "Hardcore", "Post-Hardcore", "Screamo", "Emo",
        # Punk group
        "Punk", "Pop-Punk", "Post-Punk",
        # Metal
        "Progressive Metal", "Post-Metal", "Avantgarde Metal", "Black Metal",
        "Death Metal", "Doom Metal", "Sludge Metal", "Heavy Metal", "Thrash Metal",
        "Power Metal", "Gothic Metal", "Symphonic Metal", "Industrial Metal", "Melodic Death Metal",
        # Rock & Underground
        "Indie Rock", "Progressive Rock", "Art Rock", "Post-Rock", "Noise Rock", "Math Rock",
        "Stoner Rock", "Psychedelic Rock", "Alternative Rock", "Hard Rock", "Grunge",
        "Shoegaze", "Darkwave",
        # Acoustic
        "Singer-Songwriter", "Folk", "Acoustic"
    ]

    # Relevance threshold (0-100) to notify users or mark as relevant
    MIN_RELEVANCE_SCORE: int = 40

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
