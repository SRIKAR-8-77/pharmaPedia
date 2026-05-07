#!/bin/bash
# reset.sh — Wipe all data and restart PharmaPedia from scratch.
# Run from the project root: bash reset.sh
#
# What this does:
#   1. Stops all containers and removes named volumes (postgres + redis data)
#   2. Rebuilds the backend image — installs BOTH requirements.txt and requirements-ml.txt
#   3. Starts postgres + redis, waits for healthy status
#   4. Starts the API (runs init_db / SQLAlchemy create_all on startup)
#   5. Starts Celery worker + beat
#
# Frontend: run "cd frontend && npm install && npm run dev" separately.

set -euo pipefail

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}==>${NC} $*"; }
warn()  { echo -e "${YELLOW}  ! $*${NC}"; }
error() { echo -e "${RED}ERR $*${NC}"; exit 1; }

# ── sanity checks ──────────────────────────────────────────────────────────────
[[ -f docker-compose.yml ]] || error "Run this script from the PharmaPedia project root."
command -v docker &>/dev/null  || error "Docker not found."
docker compose version &>/dev/null || error "Docker Compose v2 not found."

# ── stop and wipe ──────────────────────────────────────────────────────────────
info "Stopping all services and removing volumes..."
docker compose down --volumes --remove-orphans 2>/dev/null || true

# In case volumes were created with a different project prefix
docker volume rm pharmasignal_postgres_data pharmasignal_redis_data 2>/dev/null || true

# ── rebuild backend image ──────────────────────────────────────────────────────
info "Rebuilding backend image..."
info "  (downloads: requirements.txt + requirements-ml.txt + en_core_web_sm + en_core_sci_md + cardiffnlp sentiment model)"
info "  First build takes ~20 min — all models are baked in so containers work offline."
docker compose build --no-cache backend celery_worker celery_beat

# ── start infrastructure ───────────────────────────────────────────────────────
info "Starting postgres and redis..."
docker compose up -d postgres redis

info "Waiting for postgres to be ready..."
MAX_WAIT=60
WAITED=0
until docker compose exec -T postgres pg_isready -U pharmasignal -q 2>/dev/null; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        error "Postgres did not become ready within ${MAX_WAIT}s."
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "  postgres ready (${WAITED}s)"

info "Waiting for redis to be ready..."
WAITED=0
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        error "Redis did not become ready within ${MAX_WAIT}s."
    fi
    sleep 2
    WAITED=$((WAITED + 2))
done
echo "  redis ready (${WAITED}s)"

# ── start backend API ──────────────────────────────────────────────────────────
info "Starting backend API (init_db runs SQLAlchemy create_all on first boot)..."
docker compose up -d backend

info "Waiting for API health check..."
WAITED=0
MAX_WAIT=90
until curl -sf http://localhost:8000/health >/dev/null 2>&1; do
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        warn "API did not respond in ${MAX_WAIT}s — check logs: docker compose logs backend"
        break
    fi
    sleep 3
    WAITED=$((WAITED + 3))
done
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    echo "  API ready (${WAITED}s) — http://localhost:8000"
fi

# ── start workers ──────────────────────────────────────────────────────────────
info "Starting Celery worker and beat scheduler..."
docker compose up -d celery_worker celery_beat

# ── done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}PharmaPedia is running.${NC}"
echo "  API:      http://localhost:8000"
echo "  Docs:     http://localhost:8000/docs"
echo "  Frontend: cd frontend && npm install && npm run dev  (http://localhost:5173)"
echo ""
echo "Useful commands:"
echo "  docker compose logs -f backend       # API logs"
echo "  docker compose logs -f celery_worker # Worker logs"
echo "  docker compose logs -f celery_beat   # Beat scheduler logs"
echo "  docker compose ps                    # All service status"
echo "  docker compose down                  # Stop everything"
