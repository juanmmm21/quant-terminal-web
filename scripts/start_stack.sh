#!/usr/bin/env bash
# Arranca el stack completo: bootstrap → pipeline → tick bridge → paper bot → API → UI
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Bootstrap lakehouse (si hace falta)"
python3 scripts/bootstrap_market_data.py

echo "==> Pipeline ecosistema → data/ecosystem/"
python3 scripts/run_ecosystem_pipeline.py

echo "==> Tick bridge (background)"
python3 scripts/tick_bridge.py &
TICK_PID=$!

echo "==> Paper bot runner (background)"
python3 scripts/paper_bot_runner.py &
BOT_PID=$!

cleanup() {
  kill "$TICK_PID" "$BOT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> API (background)"
cd backend
if [[ -d .venv ]]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi
quant-terminal-api &
API_PID=$!
cd "$ROOT"

echo "==> Frontend"
echo "API: http://127.0.0.1:8000  UI: http://localhost:5173"
npm run dev
