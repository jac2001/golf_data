#!/bin/bash
# Restart the FastAPI backend (api/main.py) on port 8000
#
# Usage:
#   ./restart_api.sh

cd /Users/jacklegnon/Desktop/golf_data

PORT=8000
PID=$(lsof -ti:$PORT)
if [ -n "$PID" ]; then
  echo "Killing existing process on port $PORT (PID $PID)"
  kill -9 $PID
  sleep 1
fi

echo "Starting uvicorn on port $PORT..."
uvicorn api.main:app --reload --port $PORT
