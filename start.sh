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

# ── External services (Postgres / MinIO) ────────────────
# The backend now requires Postgres + MinIO. After the migration, these are
# NOT auto-started — this preflight brings them up via docker compose.
#
# Override behavior:
#   - SKIP_DOCKER_DEPS=1   → assume services already running externally
#   - DATABASE_URL=...     → only relevant if it points at postgres://*
#   - STORAGE_BACKEND=local→ skip MinIO startup

cd "$PROJECT_ROOT"

need_postgres=0
need_minio=0

# workbench/config.py defaults: postgresql://lijiahao:123456@localhost:5432/postgres
db_url="${DATABASE_URL:-postgresql://lijiahao:123456@localhost:5432/postgres}"
case "$db_url" in
    postgres://*|postgresql://*) need_postgres=1 ;;
esac

# default storage_backend in config.py is "minio"
storage_backend="${STORAGE_BACKEND:-minio}"
if [ "$storage_backend" = "minio" ]; then
    need_minio=1
fi

start_via_docker() {
    local svc="$1"
    if ! command -v docker >/dev/null 2>&1; then
        echo "[ERROR] $svc required but 'docker' is not installed."
        echo "        Install Docker Desktop (https://www.docker.com/products/docker-desktop)"
        echo "        or set SKIP_DOCKER_DEPS=1 after starting $svc yourself."
        exit 1
    fi
    if ! docker info >/dev/null 2>&1; then
        echo "[ERROR] $svc required but Docker daemon is not reachable."
        echo "        Start Docker Desktop, or set SKIP_DOCKER_DEPS=1 after starting $svc yourself."
        exit 1
    fi
    echo "  starting $svc via docker compose ..."
    docker compose up -d "$svc"
}

wait_for_tcp_port() {
    local host="$1" port="$2" name="$3" max="${4:-60}"
    for _ in $(seq 1 "$max"); do
        if (echo >"/dev/tcp/$host/$port") 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    echo "[ERROR] $name not reachable at $host:$port after ${max}s"
    return 1
}

wait_for_http() {
    local url="$1" name="$2" max="${3:-60}"
    for _ in $(seq 1 "$max"); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    echo "[ERROR] $name health check failed at $url after ${max}s"
    return 1
}

if [ "${SKIP_DOCKER_DEPS:-0}" != "1" ]; then
    if [ "$need_postgres" -eq 1 ] || [ "$need_minio" -eq 1 ]; then
        echo ""
        echo "ensuring external services ..."
        if [ ! -f "$PROJECT_ROOT/docker-compose.yml" ]; then
            echo "[ERROR] docker-compose.yml missing at $PROJECT_ROOT"
            exit 1
        fi
        if [ "$need_postgres" -eq 1 ]; then
            start_via_docker postgres
        fi
        if [ "$need_minio" -eq 1 ]; then
            start_via_docker minio
        fi
        # Parse host/port from DATABASE_URL (best effort).
        pg_host="localhost"
        pg_port="5432"
        if [ "$need_postgres" -eq 1 ]; then
            # strip scheme and credentials
            db_no_scheme="${db_url#*://}"
            db_no_creds="${db_no_scheme#*@}"
            db_hostport="${db_no_creds%%/*}"
            pg_host="${db_hostport%%:*}"
            if echo "$db_hostport" | grep -q ':'; then
                pg_port="${db_hostport##*:}"
            fi
            wait_for_tcp_port "$pg_host" "$pg_port" "postgres" 60 || exit 1
            echo "[OK] postgres reachable at $pg_host:$pg_port"
        fi
        if [ "$need_minio" -eq 1 ]; then
            minio_host="${MINIO_ENDPOINT:-localhost:9000}"
            # MINIO_ENDPOINT may be "host:port" or just "host"
            case "$minio_host" in
                *:*) minio_port="${minio_host##*:}"; minio_host="${minio_host%%:*}" ;;
                *)   minio_port="9000" ;;
            esac
            wait_for_tcp_port "$minio_host" "$minio_port" "minio" 60 || exit 1
            # S3 API returns 200 on /minio/health/live once ready.
            wait_for_http "http://$minio_host:$minio_port/minio/health/live" "minio" 60 || exit 1
            echo "[OK] minio reachable at $minio_host:$minio_port"
        fi
    fi
else
    echo "[INFO] SKIP_DOCKER_DEPS=1 — assuming external services are already up"
fi

# ── Launch backend ──────────────────────────────────────
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
