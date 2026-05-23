#!/usr/bin/env bash
# audit-helpers.sh
# Shared helpers for run_audit.sh and related audit scripts.
# Sourced; not executable on its own.
# Bash 4+ required (associative arrays, mapfile).

# Guard against double-source.
if [ -n "${ARKON_AUDIT_HELPERS_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
ARKON_AUDIT_HELPERS_LOADED=1

# ---------------------------------------------------------------------------
# Excludes shared by every scanner. Keep in sync with FIND_EXCLUDES.
# .claude/ and .agent/ are skill docs + workflow scripts — scanning them
# matches our own audit rules and produces false positives.
# ---------------------------------------------------------------------------
GREP_EXCLUDES=(
  --exclude-dir=node_modules
  --exclude-dir=.git
  --exclude-dir=.claude
  --exclude-dir=.agent
  --exclude-dir=plans
  --exclude-dir=docs
  --exclude-dir=.docs_cckit
  --exclude-dir=dist
  --exclude-dir=build
  --exclude-dir=.next
  --exclude-dir=__pycache__
  --exclude-dir=.venv
  --exclude-dir=venv
  --exclude="*.md"
  --exclude="*.lock"
  --exclude="*.log"
)

FIND_EXCLUDES=(
  -not -path '*/node_modules/*'
  -not -path '*/.git/*'
  -not -path '*/.claude/*'
  -not -path '*/.agent/*'
  -not -path '*/plans/*'
  -not -path '*/docs/*'
  -not -path '*/.docs_cckit/*'
  -not -path '*/dist/*'
  -not -path '*/build/*'
  -not -path '*/.next/*'
  -not -path '*/__pycache__/*'
  -not -path '*/.venv/*'
  -not -path '*/venv/*'
)

# ---------------------------------------------------------------------------
# AI provider host allowlist (Phase 1 decision).
# Used by audit Check #3 (network calls) to filter out legitimate provider
# traffic before flagging suspicious egress.
# Keep in sync with squid/squid.conf + references/squid-whitelist-policy.md.
# ---------------------------------------------------------------------------
ALLOWED_AI_HOSTS=(
  'localhost'
  '127\.0\.0\.1'
  'host\.docker\.internal'
  'api\.openai\.com'
  'api\.anthropic\.com'
  'generativelanguage\.googleapis\.com'
  'oauth2\.googleapis\.com'
  'openrouter\.ai'
  'api\.mistral\.ai'
  'api\.cohere\.ai'
  'api\.cohere\.com'
  'api\.groq\.com'
)

# Build alternation pattern for grep -E. Hosts already escaped.
_join_alternation() {
  local IFS='|'
  echo "$*"
}
ALLOWED_HOSTS_PATTERN="$(_join_alternation "${ALLOWED_AI_HOSTS[@]}")"

# Quoted URL literal must contain a whitelisted host (or be a relative /api/ path).
# Matches strings like "https://api.openai.com/v1/...", '/api/users', `https://localhost:3000/x`.
ALLOWED_URL_PATTERN="[\"'\`](https?://(${ALLOWED_HOSTS_PATTERN})(:[0-9]+)?(/[^\"'\`[:space:]]*)?[\"'\`])|[\"'\`]/api/[a-zA-Z0-9_/.\\-]*[\"'\`]"

# ---------------------------------------------------------------------------
# Forbidden analytics / tracking packages. Used by SDK scan + patch scan.
# ---------------------------------------------------------------------------
FORBIDDEN_PKGS=(
  posthog
  mixpanel
  amplitude
  '@segment/analytics-node'
  segment
  fullstory
  hotjar
  logrocket
  datadog
  '@datadog/browser-rum'
  sentry
  '@sentry/browser'
  '@sentry/node'
  '@sentry/nextjs'
  newrelic
  google-analytics
  gtag
  heap
  pendo
  intercom
)

# Simple package-name forms (no @scope, no slash). Used for require/import
# substring matches in non-dependency files where regex word boundaries apply.
FORBIDDEN_PKG_NAMES=(
  posthog mixpanel amplitude segment fullstory hotjar logrocket
  datadog sentry newrelic 'google-analytics' gtag heap pendo intercom
)

# ---------------------------------------------------------------------------
# parse_env_value <file> <key>
# Echo the value of KEY=VALUE in <file>. Strips matching surrounding quotes
# and trailing whitespace. Empty if not found or malformed.
# Only looks at the FIRST occurrence (env files override last-write-wins, but
# audit cares whether the flag is ever set strict).
# ---------------------------------------------------------------------------
parse_env_value() {
  local file="$1" key="$2"
  [ -f "$file" ] || return 0
  # Match `KEY = value` or `KEY=value`, optional export, optional surrounding quotes.
  awk -v k="$key" '
    BEGIN { FS="=" }
    /^[[:space:]]*#/ { next }
    /^[[:space:]]*$/ { next }
    {
      line=$0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      sub(/^[[:space:]]+/, "", line)
      n=index(line, "=")
      if (n==0) next
      lhs=substr(line, 1, n-1)
      rhs=substr(line, n+1)
      sub(/[[:space:]]+$/, "", lhs)
      if (lhs != k) next
      sub(/^[[:space:]]*/, "", rhs)
      sub(/[[:space:]]+$/, "", rhs)
      # Strip matching surrounding quotes only.
      if (rhs ~ /^".*"$/) { rhs=substr(rhs, 2, length(rhs)-2) }
      else if (rhs ~ /^'\''.*'\''$/) { rhs=substr(rhs, 2, length(rhs)-2) }
      print rhs
      exit
    }
  ' "$file"
}

# ---------------------------------------------------------------------------
# check_env_flag_truthy <file...> <key> <truthy-regex>
# Returns 0 if any file has KEY matching truthy-regex (e.g. ^1$, ^(1|true)$).
# Args: trailing two are key + regex; everything before is the file list.
# ---------------------------------------------------------------------------
check_env_flag_truthy() {
  local argc=$#
  local truthy="${!argc}"
  local key_idx=$((argc - 1))
  local key="${!key_idx}"
  local last_file_idx=$((argc - 2))
  local i
  for ((i=1; i<=last_file_idx; i++)); do
    local f="${!i}"
    [ -f "$f" ] || continue
    local val
    val="$(parse_env_value "$f" "$key")"
    if [ -n "$val" ] && [[ "$val" =~ $truthy ]]; then
      return 0
    fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# jq_deps <package.json>
# Print one dependency name per line (deps + devDeps + peerDeps + optionalDeps).
# Silent fallthrough if file missing or jq parse fails.
# ---------------------------------------------------------------------------
jq_deps() {
  local f="$1"
  [ -f "$f" ] || return 0
  command -v jq >/dev/null 2>&1 || return 0
  jq -r '
    [
      (.dependencies // {}),
      (.devDependencies // {}),
      (.peerDependencies // {}),
      (.optionalDependencies // {})
    ]
    | add // {}
    | keys[]
  ' "$f" 2>/dev/null || true
}

# ---------------------------------------------------------------------------
# pkg_matches_forbidden <pkg-name>
# Exit 0 if pkg matches any FORBIDDEN_PKGS entry.
# Match rules: exact, OR substring with package-name boundary
# (e.g. "posthog-js" matches "posthog", "@sentry/nextjs" matches "@sentry/nextjs"
# and "sentry").
# ---------------------------------------------------------------------------
pkg_matches_forbidden() {
  local pkg="$1"
  local bad
  for bad in "${FORBIDDEN_PKGS[@]}"; do
    if [ "$pkg" = "$bad" ]; then return 0; fi
    # Substring with simple boundary: pkg starts/ends with bad or wraps in [-/]
    if [[ "$pkg" =~ (^|[/-])${bad}($|[/-]) ]]; then return 0; fi
  done
  return 1
}

# ---------------------------------------------------------------------------
# parse_yaml_services <docker-compose.yml>
# Emit one line per service in the form:
#   service_name|read_only|networks_csv
# read_only is "true"/"false"/"unset". networks_csv is comma-joined names or "".
# Indentation-aware but tolerant — falls back to "unset" on parse failure.
# ---------------------------------------------------------------------------
parse_yaml_services() {
  local f="$1"
  [ -f "$f" ] || return 0
  awk '
    BEGIN { in_services=0; svc=""; ro="unset"; nets=""; in_nets=0 }
    function emit() {
      if (svc != "") {
        printf "%s|%s|%s\n", svc, ro, nets
      }
      svc=""; ro="unset"; nets=""; in_nets=0
    }
    /^[[:space:]]*#/ { next }
    /^services:[[:space:]]*$/ { in_services=1; next }
    # Top-level key resets state (volumes:, networks:, secrets:, etc.)
    /^[A-Za-z_]/ && !/^services:/ { emit(); in_services=0; next }
    in_services && /^[[:space:]]{2}[A-Za-z0-9_.\-]+:[[:space:]]*$/ {
      emit()
      gsub(/[[:space:]:]/, "", $0)
      svc=$0
      in_nets=0
      next
    }
    in_services && svc != "" && /^[[:space:]]+read_only:[[:space:]]*(true|false)/ {
      if ($0 ~ /true/) ro="true"; else ro="false"
      next
    }
    in_services && svc != "" && /^[[:space:]]+networks:[[:space:]]*$/ {
      in_nets=1
      next
    }
    in_services && svc != "" && in_nets && /^[[:space:]]+-[[:space:]]+/ {
      n=$0
      sub(/^[[:space:]]+-[[:space:]]+/, "", n)
      sub(/[[:space:]]+$/, "", n)
      if (nets == "") nets=n; else nets=nets","n
      next
    }
    in_services && svc != "" && in_nets && /^[[:space:]]+[A-Za-z]+:/ {
      in_nets=0
    }
    END { emit() }
  ' "$f"
}

# ---------------------------------------------------------------------------
# yaml_has_internal_network <docker-compose.yml> <network-name>
# Returns 0 if <network-name> declares `internal: true` under networks:.
# ---------------------------------------------------------------------------
yaml_has_internal_network() {
  local f="$1" name="$2"
  [ -f "$f" ] || return 1
  awk -v target="$name" '
    BEGIN { in_networks=0; cur=""; found=0 }
    /^[[:space:]]*#/ { next }
    /^networks:[[:space:]]*$/ { in_networks=1; next }
    /^[A-Za-z_]/ && !/^networks:/ { in_networks=0; cur="" }
    in_networks && /^[[:space:]]{2}[A-Za-z0-9_.\-]+:[[:space:]]*$/ {
      cur=$0
      gsub(/[[:space:]:]/, "", cur)
      next
    }
    in_networks && cur == target && /^[[:space:]]+internal:[[:space:]]*true/ {
      found=1; exit
    }
    END { exit (found ? 0 : 1) }
  ' "$f"
}
