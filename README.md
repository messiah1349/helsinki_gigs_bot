# Helsinki Gigs Tracker & Telegram Bot

A tool to track upcoming live gigs in the Helsinki metropolitan area (Helsinki, Espoo, Vantaa), analyze and classify them using **Gemini Flash Latest**, and deliver alerts via a **Telegram Bot** and interactive **Telegram Web App (TWA)**.

🤖 **Live Telegram Bot**: [t.me/helsinki_post_gigs_bot](https://t.me/helsinki_post_gigs_bot) (`@helsinki_post_gigs_bot`)  
🌐 **Live Web App**: [https://gigs.messiah1349-apps.men](https://gigs.messiah1349-apps.men)

---

## 🎯 Target Genres
- **Metal**: Progressive, Post-Metal, Avantgarde, Black, Death, Doom, Sludge.
- **Rock & Underground**: Progressive Rock, Art Rock, Post-Rock, Noise Rock, Math Rock, Screamo, Post-Hardcore, Post-Punk.
- **Acoustic & Folk**: Singer-Songwriters, Folk, Acoustic.

---

## 🏗 Architecture & Features

1. **Venue-First Parsers (Primary Sources)**:
   - **Tavastia & Semifinal** (110+ events)
   - **Kuudes Linja** (35+ events)
   - **Ääniwalli** (30+ events)
   - **On The Rocks** (20+ events)

2. **Aggregator Parsers (Secondary Sources)**:
   - **Tiketti.fi** API & data-stream (400+ events across Helsinki, Espoo, Vantaa to supplement and catch any missed gigs).

3. **LangChain + Gemini Flash Processing Pipeline**:
   - Artist extraction & normalization.
   - Origin country extraction (`artist_country`).
   - Lineup / festival identification (`lineup_details`, `is_festival`).
   - Genre classification and relevance scoring (0-100%).
   - Natural language query filter extraction (`parse_user_query`).

4. **Telegram Bot (`aiogram 3`)**:
   - Scheduled broadcast of new relevant events (default: twice a week, configurable via cron/env).
   - Natural language search: type freeform text (e.g., *"any post-punk or doom gigs next month under 30 euros?"*) and the bot uses Gemini Flash to extract filters and query the DB.
   - `/start` to subscribe and launch the Web App.
   - `/gigs` to list immediate upcoming relevant events.

5. **Telegram Web App (TWA)**:
   - Clean dark-mode UI optimized for Telegram Web App.
   - Interactive filters: Genre dropdown, Region (Helsinki, Espoo, Vantaa), Minimum relevance score slider, Date range.
   - Built-in "Ask AI" natural language search bar.
   - Instant ticket links and lineup details.

6. **Storage & Deployment**:
   - Async SQLite with SQLAlchemy (`aiosqlite`).
   - Fast slim multi-stage Docker build (`Dockerfile` & `docker-compose.yml`).

---

## 🚀 Quickstart & Setup

### 1. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your API keys:
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstuvwx
GEMINI_API_KEY=AIzaSy...
WEBAPP_URL=https://your-public-domain-or-ngrok.com
CRON_SCHEDULE_DAYS=wed,sun
CRON_SCHEDULE_HOUR=10
CRON_SCHEDULE_MINUTE=0
MIN_RELEVANCE_SCORE=40
```

### 2. Run with Docker Compose (Recommended)
```bash
docker-compose up --build -d
```
The FastAPI server and Telegram Web App will be accessible at `http://localhost:8000`.

### 3. Run Locally (without Docker)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 🛠 Management Endpoints

- **Web App**: `GET /`
- **Gigs API**: `GET /api/gigs?genre=Post-Rock&city=Helsinki&min_score=50`
- **Natural Language Filter API**: `POST /api/query-filter`
- **Trigger Pipeline Immediately**: `POST /api/admin/run-pipeline`
