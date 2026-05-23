#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Arkon full build & deploy pipeline
#
# Usage:
#   ./deploy.sh              Build and start all services
#   ./deploy.sh --no-cache   Force full rebuild (no Docker layer cache)
#   ./deploy.sh --pull       Pull latest base images before building
#   ./deploy.sh --restart    Stop then rebuild and restart (keeps volumes)
#   ./deploy.sh --reset      Stop, REMOVE ALL DATA VOLUMES, then rebuild
#   ./deploy.sh --logs       Tail logs from all containers after deploy
#   ./deploy.sh --down       Stop and remove containers (keep volumes)
#   ./deploy.sh --status     Show current container status
#   ./deploy.sh --help       Show this help
#
# Multiple flags can be combined: ./deploy.sh --no-cache --logs
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env.docker"
ENV_EXAMPLE="$SCRIPT_DIR/.env.docker.example"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

# Timeout waiting for services to become healthy (seconds)
HEALTH_TIMEOUT=180

# ---------------------------------------------------------------------------
# Colors
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERR]${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${RESET}"; }
divider() { echo -e "${CYAN}────────────────────────────────────────────────${RESET}"; }

# ---------------------------------------------------------------------------
# Parse flags
# ---------------------------------------------------------------------------
OPT_NO_CACHE=0
OPT_PULL=0
OPT_RESTART=0
OPT_RESET=0
OPT_LOGS=0
OPT_DOWN=0
OPT_STATUS=0

for arg in "$@"; do
  case "$arg" in
    --no-cache) OPT_NO_CACHE=1 ;;
    --pull)     OPT_PULL=1 ;;
    --restart)  OPT_RESTART=1 ;;
    --reset)    OPT_RESET=1 ;;
    --logs)     OPT_LOGS=1 ;;
    --down)     OPT_DOWN=1 ;;
    --status)   OPT_STATUS=1 ;;
    --help|-h)
      sed -n '3,14p' "$0" | sed 's/^# \?//'
      exit 0
      ;;
    *)
      error "Unknown flag: $arg"
      echo "Run ./deploy.sh --help for usage."
      exit 1
      ;;
  esac
done

# ---------------------------------------------------------------------------
# Helper: resolve compose binary
# ---------------------------------------------------------------------------
compose_cmd() {
  if docker compose version &>/dev/null 2>&1; then
    docker compose "$@"
  elif command -v docker-compose &>/dev/null; then
    docker-compose "$@"
  else
    error "docker compose plugin not found. Install Docker Desktop or 'docker-compose' CLI."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# --status: just show running containers and exit
# ---------------------------------------------------------------------------
if [[ "$OPT_STATUS" -eq 1 ]]; then
  step "Container status"
  compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps 2>/dev/null || \
    compose_cmd -f "$COMPOSE_FILE" ps
  exit 0
fi

# ---------------------------------------------------------------------------
# --down: stop and remove containers
# ---------------------------------------------------------------------------
if [[ "$OPT_DOWN" -eq 1 ]]; then
  step "Stopping all containers"
  compose_cmd -f "$COMPOSE_FILE" down
  success "Containers stopped."
  exit 0
fi

# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------
divider
echo -e "${BOLD}  Arkon — Build & Deploy${RESET}"
divider

# ---------------------------------------------------------------------------
# Step 1: Check prerequisites
# ---------------------------------------------------------------------------
step "Checking prerequisites"

if ! command -v docker &>/dev/null; then
  error "Docker is not installed. Install Docker Desktop from https://www.docker.com/"
  exit 1
fi

if ! docker info &>/dev/null 2>&1; then
  error "Docker daemon is not running. Start Docker Desktop and try again."
  exit 1
fi
success "Docker $(docker --version | cut -d' ' -f3 | tr -d ',')"

if docker compose version &>/dev/null 2>&1; then
  success "docker compose $(docker compose version --short 2>/dev/null || echo 'v2')"
elif command -v docker-compose &>/dev/null; then
  success "docker-compose $(docker-compose --version | awk '{print $3}' | tr -d ',')"
else
  error "docker compose plugin not found."
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 2: Prepare .env.docker
# ---------------------------------------------------------------------------
step "Checking environment file"

if [[ ! -f "$ENV_FILE" ]]; then
  if [[ -f "$ENV_EXAMPLE" ]]; then
    warn ".env.docker not found — copying from .env.docker.example"
    cp "$ENV_EXAMPLE" "$ENV_FILE"
    echo ""
    warn "IMPORTANT: The default SECRET_KEY is insecure."
    warn "Edit .env.docker and set a strong SECRET_KEY before production use:"
    warn "  python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    echo ""
  else
    error ".env.docker not found and .env.docker.example is missing."
    error "Create .env.docker manually. See docs/DEPLOY.md for required variables."
    exit 1
  fi
fi

success ".env.docker found"

# Validate critical keys
MISSING_VARS=()
while IFS= read -r line; do
  # Skip comments and empty lines
  [[ "$line" =~ ^#.*$ || -z "$line" ]] && continue
  key="${line%%=*}"
  val="${line#*=}"
  case "$key" in
    SECRET_KEY)
      if [[ "$val" == "change-me-to-a-random-secret-string" || -z "$val" ]]; then
        warn "SECRET_KEY is still the example value — change it in .env.docker!"
      fi
      ;;
    DATABASE_URL|POSTGRES_PASSWORD|MINIO_SECRET_KEY|REDIS_PASSWORD)
      [[ -z "$val" ]] && MISSING_VARS+=("$key")
      ;;
  esac
done < "$ENV_FILE"

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
  error "Missing required variables in .env.docker: ${MISSING_VARS[*]}"
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 3: Handle --reset / --restart
# ---------------------------------------------------------------------------
if [[ "$OPT_RESET" -eq 1 ]]; then
  step "Resetting deployment (REMOVING ALL DATA VOLUMES)"
  warn "This will delete all database, Redis, and MinIO data."
  echo -n "Are you sure? Type 'yes' to confirm: "
  read -r confirm
  if [[ "$confirm" != "yes" ]]; then
    info "Reset cancelled."
    exit 0
  fi
  compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down -v --remove-orphans
  success "All containers and volumes removed"
elif [[ "$OPT_RESTART" -eq 1 ]]; then
  step "Stopping existing containers (keeping volumes)"
  compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" down --remove-orphans 2>/dev/null || true
  success "Existing containers stopped"
fi

# ---------------------------------------------------------------------------
# Step 4: Build images
# ---------------------------------------------------------------------------
step "Building Docker images"

BUILD_ARGS=()
[[ "$OPT_NO_CACHE" -eq 1 ]] && BUILD_ARGS+=("--no-cache") && info "Cache disabled (--no-cache)"
[[ "$OPT_PULL" -eq 1 ]]     && BUILD_ARGS+=("--pull")     && info "Pulling latest base images"

info "Building backend image (arkon-backend)…"
compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}" api

info "Building frontend image (arkon-frontend)…"
compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" build "${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"}" frontend

success "Images built"

# ---------------------------------------------------------------------------
# Step 5: Start services
# ---------------------------------------------------------------------------
step "Starting all services"

compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --remove-orphans

success "All containers started"

# ---------------------------------------------------------------------------
# Step 6: Wait for health checks
# ---------------------------------------------------------------------------
step "Waiting for services to become healthy (timeout: ${HEALTH_TIMEOUT}s)"

SERVICES=("arkon_postgres" "arkon_redis" "arkon_minio" "arkon_api" "arkon_frontend")
ELAPSED=0
INTERVAL=5

while [[ $ELAPSED -lt $HEALTH_TIMEOUT ]]; do
  ALL_HEALTHY=1
  UNHEALTHY=()

  for svc in "${SERVICES[@]}"; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' "$svc" 2>/dev/null || echo "missing")
    case "$STATUS" in
      healthy) ;;
      starting) ALL_HEALTHY=0; UNHEALTHY+=("$svc(starting)") ;;
      unhealthy) ALL_HEALTHY=0; UNHEALTHY+=("$svc(UNHEALTHY)") ;;
      *)
        # Container without healthcheck — just check it's running
        RUNNING=$(docker inspect --format='{{.State.Running}}' "$svc" 2>/dev/null || echo "false")
        [[ "$RUNNING" != "true" ]] && ALL_HEALTHY=0 && UNHEALTHY+=("$svc(not running)")
        ;;
    esac
  done

  if [[ $ALL_HEALTHY -eq 1 ]]; then
    break
  fi

  printf "\r${CYAN}[INFO]${RESET} Waiting… %ds — %s" "$ELAPSED" "${UNHEALTHY[*]}"
  sleep $INTERVAL
  ELAPSED=$((ELAPSED + INTERVAL))
done
echo ""

if [[ $ELAPSED -ge $HEALTH_TIMEOUT ]]; then
  error "Timed out waiting for healthy services."
  error "Check logs with: ./deploy.sh --logs"
  echo ""
  compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps
  exit 1
fi

# ---------------------------------------------------------------------------
# Step 7: Final status
# ---------------------------------------------------------------------------
divider
echo -e "${GREEN}${BOLD}  Deployment successful!${RESET}"
divider

compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" ps

# Read ports from env (with defaults)
API_PORT="5055"
FRONTEND_PORT="3119"
MINIO_CONSOLE_PORT="9003"

# Try to read ports from .env.docker
API_PORT_ENV=$(grep '^NEXT_PUBLIC_API_URL' "$ENV_FILE" 2>/dev/null | grep -oE ':[0-9]+' | tr -d ':' | head -1 || echo "")
[[ -n "$API_PORT_ENV" ]] && API_PORT="$API_PORT_ENV"

echo ""
echo -e "  ${BOLD}Access URLs:${RESET}"
echo -e "  Frontend (Admin UI)  →  ${GREEN}http://localhost:${FRONTEND_PORT}${RESET}"
echo -e "  Backend API          →  ${GREEN}http://localhost:${API_PORT}${RESET}"
echo -e "  API Docs (Swagger)   →  ${GREEN}http://localhost:${API_PORT}/docs${RESET}"
echo -e "  MinIO Console        →  ${GREEN}http://localhost:${MINIO_CONSOLE_PORT}${RESET}"

# Show default admin credentials from .env
ADMIN_EMAIL=$(grep '^DEFAULT_ADMIN_EMAIL' "$ENV_FILE" 2>/dev/null | cut -d'=' -f2 || echo "admin@arkon.local")
echo ""
echo -e "  ${BOLD}Default admin login:${RESET}"
echo -e "  Email    →  ${ADMIN_EMAIL}"
echo -e "  Password →  (set in .env.docker as DEFAULT_ADMIN_PASSWORD)"
divider

# ---------------------------------------------------------------------------
# Step 8: Optionally tail logs
# ---------------------------------------------------------------------------
if [[ "$OPT_LOGS" -eq 1 ]]; then
  step "Tailing logs (Ctrl+C to stop)"
  compose_cmd -f "$COMPOSE_FILE" --env-file "$ENV_FILE" logs -f
fi
