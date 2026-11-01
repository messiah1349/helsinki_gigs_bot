#!/usr/bin/env bash
set -e

# Change to project root directory
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# Ensure log file directory exists
mkdir -p "$PROJECT_DIR/data"

echo "Checking if helsinki_gigs is already running..."
if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "helsinki_gigs is already running! (PID: $(pgrep -f 'uvicorn app.main:app'))"
    exit 0
fi

echo "Starting Helsinki Gigs Telegram Bot & WebApp on port 8000..."
nohup "$PROJECT_DIR/.venv/bin/uvicorn" app.main:app --host 0.0.0.0 --port 8000 >> "$PROJECT_DIR/app.log" 2>&1 &

sleep 2

if pgrep -f "uvicorn app.main:app" > /dev/null; then
    echo "✅ Helsinki Gigs successfully started! (PID: $(pgrep -f 'uvicorn app.main:app'))"
    echo "Logs: tail -f $PROJECT_DIR/app.log"
else
    echo "❌ Failed to start. Check $PROJECT_DIR/app.log for details."
    exit 1
fi
