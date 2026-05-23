#!/usr/bin/env bash
# Update Arkon's llm_base_url (and optionally embedding endpoint) when the
# local LLM server (e.g. LM Studio) moves to a new IP / port.
#
# Usage:
#   scripts/set-llm-endpoint.sh <ip-or-host[:port]>           # defaults port 1234
#   scripts/set-llm-endpoint.sh http://192.168.1.6:1234/v1    # full url ok
#   scripts/set-llm-endpoint.sh                                 # interactive
#
# Steps:
#   1. Normalize input → http://<host>:<port>/v1
#   2. Curl /v1/models to confirm reachability (5s timeout)
#   3. UPDATE app_config SET value=... WHERE key='llm_base_url' (via psql in
#      arkon_postgres container). Plaintext — llm_base_url is NOT in the
#      sensitive-keys list, so no Fernet round-trip needed.
#   4. Show models so user can confirm the expected model is loaded.
#
# Notes:
#   - llm_api_key is encrypted at rest; we do not touch it.
#   - LLMProvider reads llm_base_url lazily, so no service restart needed.

set -euo pipefail

PG_CONTAINER="${PG_CONTAINER:-arkon_postgres}"
PG_USER="${PG_USER:-arkon}"
PG_DB="${PG_DB:-arkon}"
DEFAULT_PORT="${DEFAULT_PORT:-1234}"
CURL_TIMEOUT="${CURL_TIMEOUT:-5}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*" >&2; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

INPUT="${1:-}"
if [[ -z "$INPUT" ]]; then
  read -rp "LLM host (ip or ip:port or full url): " INPUT
fi
if [[ -z "$INPUT" ]]; then
  red "No input given. Aborting."; exit 1
fi

# Strip scheme + /v1 suffix
RAW="${INPUT#http://}"
RAW="${RAW#https://}"
RAW="${RAW%/v1}"
RAW="${RAW%/}"

# Split host:port
if [[ "$RAW" == *:* ]]; then
  HOST="${RAW%%:*}"
  PORT="${RAW##*:}"
else
  HOST="$RAW"
  PORT="$DEFAULT_PORT"
fi

if [[ -z "$HOST" || -z "$PORT" ]]; then
  red "Could not parse host/port from '$INPUT'"; exit 1
fi

NEW_URL="http://${HOST}:${PORT}/v1"

bold "Target endpoint: $NEW_URL"

# 1. Reachability probe
if ! curl -fsS -m "$CURL_TIMEOUT" "${NEW_URL}/models" -o /tmp/llm-models.$$.json; then
  red "Endpoint not reachable within ${CURL_TIMEOUT}s. Update aborted."
  rm -f /tmp/llm-models.$$.json
  exit 2
fi

MODEL_LIST=$(python3 -c "
import json,sys
data=json.load(open('/tmp/llm-models.$$.json'))
ids=[m.get('id') for m in data.get('data',[])]
print('\n'.join(ids))
" 2>/dev/null || true)
rm -f /tmp/llm-models.$$.json

green "Reachable. Models advertised:"
echo "$MODEL_LIST" | sed 's/^/  - /'

# 2. Read current value
OLD=$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc \
  "SELECT value FROM app_config WHERE key='llm_base_url';" 2>/dev/null || true)
OLD="${OLD//[$'\t\r\n ']}"

if [[ "$OLD" == "$NEW_URL" ]]; then
  yellow "llm_base_url already = $NEW_URL — nothing to do."
  exit 0
fi

bold "DB update:"
printf "  old: %s\n  new: %s\n" "${OLD:-<unset>}" "$NEW_URL"

# 3. UPSERT
docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -c "
INSERT INTO app_config (key, value)
VALUES ('llm_base_url', '$NEW_URL')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
" > /dev/null

green "llm_base_url updated."

# 4. Sync sibling endpoints (embedding + vision) since LM Studio commonly serves
#    all three from the same host. Flag --no-sync skips this; ARKON_SYNC_SIBLINGS=0
#    works the same way for non-interactive (CI) callers.
SYNC_SIBLINGS="${ARKON_SYNC_SIBLINGS:-1}"
if [[ "${2:-}" == "--no-sync" ]]; then SYNC_SIBLINGS=0; fi

if [[ "$SYNC_SIBLINGS" == "1" ]]; then
  for SIBLING in embedding_base_url vision_base_url; do
    SIB_OLD=$(docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -tAc \
      "SELECT value FROM app_config WHERE key='$SIBLING';" 2>/dev/null || true)
    SIB_OLD="${SIB_OLD//[$'\t\r\n ']}"
    if [[ -n "$SIB_OLD" && "$SIB_OLD" != "$NEW_URL" ]]; then
      docker exec "$PG_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -c "
UPDATE app_config SET value='$NEW_URL' WHERE key='$SIBLING';
" > /dev/null
      green "$SIBLING updated (was: $SIB_OLD)."
    fi
  done
fi

green "Done. Arkon LLMProvider re-reads config on next request — no restart needed."
