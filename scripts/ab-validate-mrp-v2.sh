#!/usr/bin/env bash
# ab-validate-mrp-v2.sh — A/B validation harness for MRP v2 (local profile)
#
# Usage:
#   ./scripts/ab-validate-mrp-v2.sh <source_uuid> [<source_uuid> ...] [--confirm-prod]
#
# What it does (Phase 9):
#   1. Validates each arg is a UUID.
#   2. Refuses prod-pattern DATABASE_URL unless --confirm-prod is passed.
#   3. Sets `app_config.mrp.intake_paused = 'true'` so workers re-enqueue
#      live jobs for +60s while we manipulate state.
#   4. For each source: pg_dump baseline to plans/baselines/<id>.sql,
#      DELETE its wiki_pages (not UPDATE-to-stub — never serve a fake-fail
#      page to live users), then call existing regen-failed-source script.
#   5. Polls source.status until ready/failed (30 min timeout).
#   6. Unsets the pause flag (also on trap EXIT for safety).
#   7. Prints fail-marker count + orphan sanity check.
#
# Requires: psql, pg_dump, python (with arkon venv on PATH or DATABASE_URL set).
set -euo pipefail

CONFIRM_PROD=0
SOURCE_IDS=()

for arg in "$@"; do
  case "$arg" in
    --confirm-prod) CONFIRM_PROD=1 ;;
    *) SOURCE_IDS+=("$arg") ;;
  esac
done

if [[ ${#SOURCE_IDS[@]} -eq 0 ]]; then
  echo "usage: $0 <source_uuid> [...] [--confirm-prod]" >&2
  exit 2
fi

# --- UUID validation -------------------------------------------------------
for sid in "${SOURCE_IDS[@]}"; do
  if ! python3 -c "import uuid,sys; uuid.UUID(sys.argv[1])" "$sid" >/dev/null 2>&1; then
    echo "FATAL: not a UUID: $sid" >&2
    exit 2
  fi
done

# --- Prod guard ------------------------------------------------------------
DATABASE_URL="${DATABASE_URL:-}"
if [[ -z "$DATABASE_URL" ]]; then
  echo "FATAL: DATABASE_URL is not set" >&2
  exit 2
fi
if [[ "$CONFIRM_PROD" -eq 0 ]]; then
  case "$DATABASE_URL" in
    *prod*|*production*|*amazonaws*|*supabase.co*|*neon.tech*)
      echo "FATAL: DATABASE_URL looks like prod; pass --confirm-prod to override" >&2
      exit 2
      ;;
  esac
fi

# --- Pause hook + safety trap ---------------------------------------------
psql_url() { psql "$DATABASE_URL" "$@"; }

cleanup() {
  echo "[trap] unpausing intake"
  psql_url -v ON_ERROR_STOP=1 -c \
    "INSERT INTO app_config (key,value) VALUES ('mrp.intake_paused','false') ON CONFLICT (key) DO UPDATE SET value='false';" \
    || true
}
trap cleanup EXIT INT TERM

echo "[1/5] pause intake"
psql_url -v ON_ERROR_STOP=1 -c \
  "INSERT INTO app_config (key,value) VALUES ('mrp.intake_paused','true') ON CONFLICT (key) DO UPDATE SET value='true';"

# --- Per-source baseline + regen ------------------------------------------
BASELINE_DIR="plans/260524-0110-local-llm-mrp-overhaul/baselines"
mkdir -p "$BASELINE_DIR"

for sid in "${SOURCE_IDS[@]}"; do
  echo "[2/5] baseline source=$sid"
  pg_dump --no-owner --data-only \
    --table=wiki_pages \
    "$DATABASE_URL" \
    > "$BASELINE_DIR/$sid.sql" || {
      echo "WARN: pg_dump failed for $sid (continuing)" >&2
    }

  echo "[3/5] DELETE wiki_pages for $sid"
  psql_url -v ON_ERROR_STOP=1 -c \
    "DELETE FROM wiki_pages WHERE source_ids @> jsonb_build_array('$sid'::text);"

  echo "[3.5/5] enqueue regen via existing script"
  # F3 fix: dashes are not valid in Python module names — invoke script directly.
  python3 scripts/regen-failed-source.py "$sid" || {
    echo "WARN: regen script returned non-zero for $sid (continuing)" >&2
  }
done

# --- Poll until ready/failed (30 min timeout per id) ----------------------
DEADLINE=$(( $(date +%s) + 1800 ))
for sid in "${SOURCE_IDS[@]}"; do
  echo "[4/5] poll source=$sid"
  while :; do
    status=$(psql_url -At -c "SELECT status FROM sources WHERE id='$sid'")
    if [[ "$status" == "ready" || "$status" == "failed" ]]; then
      echo "  → $sid status=$status"
      break
    fi
    if [[ $(date +%s) -ge $DEADLINE ]]; then
      echo "  → $sid TIMEOUT (last status=$status)"
      break
    fi
    sleep 10
  done
done

# --- Summary --------------------------------------------------------------
echo "[5/5] fail-marker count (must be 0):"
psql_url -At -c \
  "SELECT COUNT(*) FROM wiki_pages WHERE content_md LIKE '%Page generation failed%';"

echo "[5/5] orphan processing sanity (must be empty):"
psql_url -c \
  "SELECT id, status, updated_at FROM sources
    WHERE status='processing' AND updated_at < NOW() - INTERVAL '5 minutes';"

echo "DONE — review baselines in $BASELINE_DIR"
