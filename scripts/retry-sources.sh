#!/usr/bin/env bash
# retry-sources.sh — Retry Arkon MRP pipeline for one, many, or all sources
#
# Usage:
#   ./retry-sources.sh                          # Retry all sources in error/plan_ready
#   ./retry-sources.sh --all                    # Force-reset ALL sources and retry (even ready)
#   ./retry-sources.sh <id1> [<id2> ...]        # Retry specific source IDs
#   ./retry-sources.sh --list                   # List all sources with status (no retry)
#   ./retry-sources.sh --watch <id>             # Watch progress of a single source
#   ./retry-sources.sh --set-timeout            # Apply timeout env vars to .env.docker + restart worker
#   ./retry-sources.sh --set-timeout --dedup 600 --reconcile 300 --planning 900
#   ./retry-sources.sh --drain-ram              # Force-unload all LM Studio models + free RAM (standalone)
#   ./retry-sources.sh --drain-ram <id1> ...    # Drain RAM then retry source(s)
#
# Env overrides:
#   ARKON_URL           e.g. http://localhost:5055
#   ARKON_EMAIL         admin email
#   ARKON_PASSWORD      admin password
#   POLL_INTERVAL       poll seconds (default 10)

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env.docker"

ARKON_URL="${ARKON_URL:-http://localhost:5055}"
ARKON_EMAIL="${ARKON_EMAIL:-}"
ARKON_PASSWORD="${ARKON_PASSWORD:-}"
POLL_INTERVAL="${POLL_INTERVAL:-10}"

DOCKER_CONTAINER="${DOCKER_CONTAINER:-arkon_postgres}"
WORKER_CONTAINER="${WORKER_CONTAINER:-arkon_worker}"    # docker container name
WORKER_SERVICE="${WORKER_SERVICE:-worker}"              # docker compose service name
DB_USER="${DB_USER:-arkon}"
DB_NAME="${DB_NAME:-arkon}"

# MRP timeout defaults (can be overridden with --dedup / --reconcile / --planning)
OPT_DEDUP=600
OPT_RECONCILE=300
OPT_PLANNING=900

# Read credentials from .env.docker if not set via env
if [[ -f "$ENV_FILE" ]]; then
  [[ -z "$ARKON_EMAIL" ]]    && ARKON_EMAIL=$(grep -E '^DEFAULT_ADMIN_EMAIL='    "$ENV_FILE" | cut -d= -f2 | tr -d '"' || true)
  [[ -z "$ARKON_PASSWORD" ]] && ARKON_PASSWORD=$(grep -E '^DEFAULT_ADMIN_PASSWORD=' "$ENV_FILE" | cut -d= -f2 | tr -d '"' || true)
fi
ARKON_EMAIL="${ARKON_EMAIL:-admin@arkon.local}"
ARKON_PASSWORD="${ARKON_PASSWORD:-admin123}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
warn() { echo "[$(date '+%H:%M:%S')] WARN: $*" >&2; }
die()  { echo "[$(date '+%H:%M:%S')] ERROR: $*" >&2; exit 1; }

db_query() {
  docker exec "$DOCKER_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -t -A -c "$1"
}

get_token() {
  local token
  token=$(curl -s -X POST "$ARKON_URL/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$ARKON_EMAIL\",\"password\":\"$ARKON_PASSWORD\"}" \
    | jq -r '.access_token // empty')
  [[ -z "$token" ]] && die "Login failed — check ARKON_EMAIL / ARKON_PASSWORD"
  echo "$token"
}

list_sources() {
  db_query "SELECT id||'|'||COALESCE(title,file_name,'<untitled>')||'|'||status||'|'||COALESCE(pipeline_phase,'–') FROM sources ORDER BY created_at DESC;"
}

print_sources_table() {
  echo ""
  printf "%-38s  %-42s  %-12s  %-10s\n" "ID" "TITLE" "STATUS" "PHASE"
  printf '%s\n' "$(printf '─%.0s' $(seq 1 110))"
  while IFS='|' read -r id title status phase; do
    printf "%-38s  %-42s  %-12s  %-10s\n" "$id" "${title:0:42}" "$status" "$phase"
  done < <(list_sources)
  echo ""
}

force_reset_source() {
  local id="$1"
  db_query "UPDATE sources SET status='error', error_message='Manual reset for retry', progress=0 WHERE id='$id';" > /dev/null
  log "  Force-reset $id → error"
}

call_retry() {
  local id="$1" token="$2"
  local resp
  resp=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    "$ARKON_URL/api/sources/$id/retry" \
    -H "Authorization: Bearer $token")
  if [[ "$resp" == "200" ]]; then
    log "  ✓ Queued: $id"
  else
    warn "  ✗ HTTP $resp for $id (not in retryable status — use --all to force)"
  fi
}

watch_source() {
  local id="$1"
  log "Watching $id (Ctrl+C to stop)..."
  local last=""
  while true; do
    local row
    row=$(db_query "SELECT status||'|'||COALESCE(pipeline_phase,'–')||'|'||progress||'%|'||COALESCE(progress_message,'') FROM sources WHERE id='$id';" | tr -d ' ')
    if [[ "$row" != "$last" ]]; then
      log "  $row"
      last="$row"
    fi
    if echo "$row" | grep -qE "^ready\||^error\|"; then
      log "Finished: $row"
      break
    fi
    sleep "$POLL_INTERVAL"
  done
}

apply_timeouts() {
  local dedup="$1" reconcile="$2" planning="$3"
  [[ ! -f "$ENV_FILE" ]] && die ".env.docker not found at $ENV_FILE"

  # Remove existing MRP_TIMEOUT_* lines and re-append
  local tmp
  tmp=$(mktemp)
  grep -v '^MRP_TIMEOUT_' "$ENV_FILE" > "$tmp"
  cat >> "$tmp" <<EOF

# --- MRP Pipeline LLM timeouts ---
MRP_TIMEOUT_DEDUP=$dedup
MRP_TIMEOUT_RECONCILE=$reconcile
MRP_TIMEOUT_PLANNING=$planning
EOF
  mv "$tmp" "$ENV_FILE"
  log "Updated .env.docker: dedup=${dedup}s  reconcile=${reconcile}s  planning=${planning}s"

  log "Recreating worker container to apply new env vars..."
  # 'restart' preserves old env — 'up -d' recreates the container with new values
  docker compose --env-file "$ENV_FILE" up -d "$WORKER_SERVICE" 2>&1 | tail -3
  sleep 5
  log "Worker recreated. Verifying:"
  docker exec "$WORKER_CONTAINER" env | grep MRP_TIMEOUT || warn "No MRP_TIMEOUT vars found in container"
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
MODE="auto"    # auto | all | ids | list | watch | set-timeout | drain-ram
TARGET_IDS=()
DRAIN_FIRST=false   # --drain-ram combined with ids/all

while [[ $# -gt 0 ]]; do
  case "$1" in
    --all)         MODE="all"; shift ;;
    --list)        MODE="list"; shift ;;
    --watch)       MODE="watch"; shift; TARGET_IDS=("$1"); shift ;;
    --set-timeout) MODE="set-timeout"; shift ;;
    --drain-ram)
      # If next arg is an ID or --all, drain first then retry; else standalone drain.
      if [[ ${2:-} == --all || ${2:-} =~ ^[0-9a-f-]{36}$ ]]; then
        DRAIN_FIRST=true
      else
        MODE="drain-ram"
      fi
      shift ;;
    --dedup)       OPT_DEDUP="$2"; shift 2 ;;
    --reconcile)   OPT_RECONCILE="$2"; shift 2 ;;
    --planning)    OPT_PLANNING="$2"; shift 2 ;;
    -h|--help)
      head -24 "$0" | tail -22
      exit 0 ;;
    -*)
      die "Unknown option: $1 (run with --help)" ;;
    *)
      MODE="ids"
      TARGET_IDS+=("$1")
      shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Execute
# ---------------------------------------------------------------------------

# --list
if [[ "$MODE" == "list" ]]; then
  print_sources_table
  exit 0
fi

# --watch
if [[ "$MODE" == "watch" ]]; then
  [[ ${#TARGET_IDS[@]} -eq 0 ]] && die "--watch requires a source ID"
  watch_source "${TARGET_IDS[0]}"
  exit 0
fi

# --set-timeout
if [[ "$MODE" == "set-timeout" ]]; then
  apply_timeouts "$OPT_DEDUP" "$OPT_RECONCILE" "$OPT_PLANNING"
  exit 0
fi

# --- Auth ---
log "Authenticating as $ARKON_EMAIL..."
TOKEN=$(get_token)
log "Token OK (${#TOKEN} chars)"

# --drain-ram (standalone — no source IDs)
if [[ "$MODE" == "drain-ram" ]]; then
  log "Draining LM Studio RAM via API..."
  DRAIN_RESP=$(curl -s -X POST "$ARKON_URL/api/admin/local-ai/drain-ram" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"wait_s": 30, "kill_on_timeout": true}')
  MSG=$(echo "$DRAIN_RESP" | jq -r '.message // .detail // "(no message)"')
  RAM=$(echo "$DRAIN_RESP" | jq -r '.ram_released // "?"')
  KILLED=$(echo "$DRAIN_RESP" | jq -r '.killed // "?"')
  log "  ram_released=${RAM}  killed=${KILLED}"
  log "  $MSG"
  exit 0
fi

# --- Resolve IDs ---
if [[ "$MODE" == "all" ]]; then
  log "Mode: ALL sources (force-reset non-retryable first)"
  TARGET_IDS=( $(db_query "SELECT id FROM sources;" | tr -d ' ') )
elif [[ "$MODE" == "auto" ]]; then
  log "Mode: AUTO — retrying sources in error/plan_ready"
  TARGET_IDS=( $(db_query "SELECT id FROM sources WHERE status IN ('error','plan_ready');" | tr -d ' ') )
fi

if [[ ${#TARGET_IDS[@]} -eq 0 ]]; then
  log "No sources to retry."
  print_sources_table
  exit 0
fi

log "Targeting ${#TARGET_IDS[@]} source(s):"
for id in "${TARGET_IDS[@]}"; do
  row=$(db_query "SELECT COALESCE(title,file_name,'<untitled>')||' ['||status||']' FROM sources WHERE id='$id';" | sed 's/^ *//')
  log "  • $id  $row"
done
echo ""

# Force-reset non-retryable sources when --all
if [[ "$MODE" == "all" ]]; then
  for id in "${TARGET_IDS[@]}"; do
    local_status=$(db_query "SELECT status FROM sources WHERE id='$id';" | tr -d ' ')
    if [[ "$local_status" != "error" && "$local_status" != "plan_ready" ]]; then
      force_reset_source "$id"
    fi
  done
fi

# --- Drain RAM first (--drain-ram <ids> or --drain-ram --all) ---
if [[ "$DRAIN_FIRST" == "true" ]]; then
  log "Draining LM Studio RAM before retry..."
  DRAIN_RESP=$(curl -s -X POST "$ARKON_URL/api/admin/local-ai/drain-ram" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"wait_s": 30, "kill_on_timeout": true}')
  MSG=$(echo "$DRAIN_RESP" | jq -r '.message // .detail // "(no message)"')
  RAM=$(echo "$DRAIN_RESP" | jq -r '.ram_released // "?"')
  log "  drain result: ram_released=${RAM} — $MSG"
  if [[ "$RAM" != "true" ]]; then
    warn "RAM may not be fully released. Proceeding anyway..."
  fi
  echo ""
fi

# --- Call retry ---
log "Calling retry endpoint..."
for id in "${TARGET_IDS[@]}"; do
  call_retry "$id" "$TOKEN"
done

echo ""

# --- Watch progress ---
if [[ ${#TARGET_IDS[@]} -eq 1 ]]; then
  watch_source "${TARGET_IDS[0]}"
else
  log "Watching ${#TARGET_IDS[@]} sources (Ctrl+C to stop)..."
  while true; do
    echo ""
    for id in "${TARGET_IDS[@]}"; do
      row=$(db_query "SELECT status||'|'||COALESCE(pipeline_phase,'–')||'|'||progress||'%|'||COALESCE(progress_message,'') FROM sources WHERE id='$id';" | tr -d ' ')
      log "  $id  $row"
    done
    ids_sql="ARRAY['$(IFS="','"; echo "${TARGET_IDS[*]}")']::uuid[]"
    pending=$(db_query "SELECT COUNT(*) FROM sources WHERE id = ANY($ids_sql) AND status NOT IN ('ready','error');" | tr -d ' ')
    [[ "$pending" == "0" ]] && { log "All sources finished."; break; }
    sleep "$POLL_INTERVAL"
  done
fi

# --- Final summary ---
echo ""
log "Final status:"
for id in "${TARGET_IDS[@]}"; do
  row=$(db_query "SELECT COALESCE(title,file_name,'<id>')||' → '||status||' ('||COALESCE(pipeline_phase,'–')||') '||COALESCE(error_message,'') FROM sources WHERE id='$id';" | sed 's/^ *//')
  log "  $row"
done
