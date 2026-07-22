#!/usr/bin/env bash
# SUPATH — double-click launcher (macOS: double-click in Finder.
# Linux: right-click → Run, or double-click if your file manager allows it).
#
# Installs what's missing, starts the server, and opens Chrome once it's ready.
set -euo pipefail
cd "$(dirname "$0")"

echo "=================================================="
echo "  SUPATH — Strategic Energy Transit Unit"
echo "=================================================="
echo
echo "Installing dependencies (first run only takes a minute)…"
python3 -m pip install -r requirements.txt --break-system-packages -q 2>/dev/null \
  || python3 -m pip install -r requirements.txt -q
python3 scripts/install_abce.py

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi
if [ -f .env ]; then
  set -a; source .env; set +a
fi

open_browser() {
  sleep 2.5
  if command -v open >/dev/null 2>&1; then                 # macOS
    open -a "Google Chrome" http://localhost:8000 2>/dev/null || open http://localhost:8000
  elif command -v xdg-open >/dev/null 2>&1; then            # Linux
    xdg-open http://localhost:8000 2>/dev/null || true
  fi
}
open_browser &

echo
echo "Starting SUPATH at http://localhost:8000"
echo "Chrome will open automatically in a couple of seconds."
echo "Leave this window open — closing it stops the server."
echo

exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
