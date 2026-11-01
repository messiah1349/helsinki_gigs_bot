#!/usr/bin/env bash

echo "Stopping Helsinki Gigs..."
PIDS=$(pgrep -f "uvicorn app.main:app")

if [ -z "$PIDS" ]; then
    echo "helsinki_gigs is not running."
else
    kill $PIDS
    sleep 1
    echo "Stopped."
fi
