#!/usr/bin/env bash
# SUPATH — setup and launch.
#
#   ./run.sh
#
# Installs dependencies (including a patched abcEconomics — see
# scripts/install_abce.py for why that needs a patch at all), then starts the
# API + frontend on http://localhost:8000.
set -euo pipefail
cd "$(dirname "$0")"

echo "== SUPATH — installing dependencies =="
pip install -r requirements.txt --break-system-packages -q
python3 scripts/install_abce.py

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "Created .env from .env.example — add API keys there for live data."
fi

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "== SUPATH — starting server on http://localhost:8000 =="
exec python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
