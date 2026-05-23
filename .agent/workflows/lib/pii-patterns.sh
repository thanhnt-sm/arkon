#!/usr/bin/env bash
# pii-patterns.sh
# PII detection constants + host classifier used by Check #10 in run_audit.sh.
# Sourced; depends on audit-helpers.sh for ALLOWED_AI_HOSTS.

if [ -n "${ARKON_PII_PATTERNS_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
ARKON_PII_PATTERNS_LOADED=1

# Source audit-helpers if the caller didn't already.
if [ -z "${ARKON_AUDIT_HELPERS_LOADED:-}" ]; then
  # shellcheck source=audit-helpers.sh
  source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/audit-helpers.sh"
fi

# ---------------------------------------------------------------------------
# PII keywords. A network call carrying one of these substrings in the SAME
# line (typically as a request body field or query string) triggers the
# check. Keep this list short — false positives matter more than coverage at
# the casual threat-model level.
# ---------------------------------------------------------------------------
PII_KEYWORDS=(
  email
  password
  token
  secret
  cookie
  session
  authorization
  bearer
  user_id
  userId
  username
  phone
  ssn
  apikey
  api_key
)

# Build a single grep -E alternation for matching. Uses join_pipe from
# audit-helpers.sh (sourced above).
PII_KEYWORD_RE="$(join_pipe "${PII_KEYWORDS[@]}")"

# Network entrypoints that ship a body — `fetch(...)`, `axios.post(...)`,
# `requests.post(...)`, `httpx.post(...)`, `sendBeacon(...)`, WebSocket sends.
PII_NETWORK_RE='(fetch\(|axios\.(post|put|patch)|requests\.(post|put|patch)|httpx\.(post|put|patch)|sendBeacon|WebSocket\(.+\.send)'

# ---------------------------------------------------------------------------
# is_ai_provider_host <host>
# Returns 0 if host belongs to the audit's allowlist of AI providers (LLM,
# embed, rerank, OAuth token endpoint). Strips an optional :port suffix.
# ---------------------------------------------------------------------------
is_ai_provider_host() {
  local host="${1%%:*}"
  local entry
  for entry in "${ALLOWED_AI_HOSTS[@]}"; do
    # ALLOWED_AI_HOSTS entries are already regex-escaped (literal dots).
    # Compare against the plain host using a regex match.
    if [[ "$host" =~ ^${entry}$ ]]; then
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# is_internal_host <host>
# Loopback / docker-internal targets that don't egress.
# ---------------------------------------------------------------------------
is_internal_host() {
  local host="${1%%:*}"
  case "$host" in
    localhost|127.0.0.1|0.0.0.0|host.docker.internal|::1) return 0 ;;
  esac
  return 1
}

# ---------------------------------------------------------------------------
# extract_url_host <line>
# Pull the first quoted `http(s)://...` literal's host out of a code line.
# Empty if none found.
# ---------------------------------------------------------------------------
extract_url_host() {
  local line="$1"
  local url
  url=$(echo "$line" | grep -oE 'https?://[^"'\''`[:space:])>]+' | head -1)
  [ -z "$url" ] && { echo ""; return 0; }
  echo "$url" | sed -E 's|https?://([^/]+).*|\1|'
}
