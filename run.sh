#!/usr/bin/env bash
# One-shot launcher. Starts the backend on :8766 and the Vite dev server on :5174.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "▶ creating python venv"
  python3 -m venv .venv
  ./.venv/bin/pip install -q --upgrade pip
  ./.venv/bin/pip install -q -r requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "▶ installing frontend deps"
  (cd frontend && npm install --silent)
fi

echo "▶ starting backend  → http://127.0.0.1:8766"
./.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8766 --log-level warning &
BACKEND_PID=$!

cleanup() {
  echo "▶ shutting down"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2

echo "▶ starting frontend → http://127.0.0.1:5174"
(cd frontend && ./node_modules/.bin/vite --host 127.0.0.1 --port 5174) &
FRONTEND_PID=$!

wait
