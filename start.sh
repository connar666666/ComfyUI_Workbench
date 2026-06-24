#!/usr/bin/env bash
set -euo pipefail

# ── Config ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
WEB_DIR="$PROJECT_ROOT/web"

BACKEND_HOST="${WORKBENCH_HOST:-0.0.0.0}"
BACKEND_PORT="${WORKBENCH_PORT:-8090}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
FRONTEND_PORT="${FRONTEND_PORT:-8088}"
COMFYUI_URL="${COMFYUI_URL:-http://192.168.7.75:8188}"
WORKBENCH_ROOT="${WORKBENCH_ROOT:-$HOME/.openclaw/shared-workbench}"

PID_BACKEND=""
PID_FRONTEND=""

# ── Cleanup ─────────────────────────────────────────────
cleanup() {
    echo ""
    echo "shutting down ..."
    if [ -n "$PID_FRONTEND" ] && kill -0 "$PID_FRONTEND" 2>/dev/null; then
        kill "$PID_FRONTEND" 2>/dev/null || true
        wait "$PID_FRONTEND" 2>/dev/null || true
        echo "  frontend stopped"
    fi
    if [ -n "$PID_BACKEND" ] && kill -0 "$PID_BACKEND" 2>/dev/null; then
        kill "$PID_BACKEND" 2>/dev/null || true
        wait "$PID_BACKEND" 2>/dev/null || true
        echo "  backend stopped"
    fi
    echo "done."
}
trap cleanup EXIT INT TERM

# ── Preflight ───────────────────────────────────────────
echo "──────────────────────────────────────────────"
echo "  ComfyUI Workbench"
echo "──────────────────────────────────────────────"
echo "  project root : $PROJECT_ROOT"
echo "  backend      : http://$BACKEND_HOST:$BACKEND_PORT"
echo "  frontend     : http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "  comfyui      : $COMFYUI_URL"
echo "  storage      : $WORKBENCH_ROOT"
echo "──────────────────────────────────────────────"

cd "$PROJECT_ROOT"

# ── Python deps ─────────────────────────────────────────
if ! command -v uv &>/dev/null; then
    echo "[ERROR] uv not found — install from https://docs.astral.sh/uv/"
    exit 1
fi
uv sync --quiet 2>/dev/null || uv sync
echo "[OK] python dependencies"

# ── Node deps ───────────────────────────────────────────
if ! command -v node &>/dev/null; then
    echo "[ERROR] node not found"
    exit 1
fi
cd "$WEB_DIR"
if [ ! -d "node_modules" ]; then
    npm install --silent
fi
echo "[OK] node dependencies"

# ── Launch backend ──────────────────────────────────────
cd "$PROJECT_ROOT"
echo ""
echo "starting backend ..."
COMFYUI_URL="$COMFYUI_URL" \
WORKBENCH_ROOT="$WORKBENCH_ROOT" \
    uv run python -c "
import uvicorn
from workbench.main import app
uvicorn.run(app, host='$BACKEND_HOST', port=$BACKEND_PORT, log_level='info')
" &
PID_BACKEND=$!
echo "  backend pid=$PID_BACKEND"

# wait for backend to be ready
for i in $(seq 1 30); do
    if curl -s "http://127.0.0.1:$BACKEND_PORT/api/health" >/dev/null 2>&1; then
        echo "[OK] backend ready"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[WARN] backend not responding after 30s, continuing anyway"
    fi
    sleep 1
done

# ── Launch frontend ─────────────────────────────────────
cd "$WEB_DIR"
echo ""
echo "starting frontend ..."
npx vite --host "$FRONTEND_HOST" --port "$FRONTEND_PORT" &
PID_FRONTEND=$!
echo "  frontend pid=$PID_FRONTEND"

echo ""
echo "──────────────────────────────────────────────"
echo "  backend  → http://$BACKEND_HOST:$BACKEND_PORT"
echo "  frontend → http://$FRONTEND_HOST:$FRONTEND_PORT"
echo "  press Ctrl+C to stop"
echo "──────────────────────────────────────────────"
echo ""

# ── Wait ────────────────────────────────────────────────
wait
