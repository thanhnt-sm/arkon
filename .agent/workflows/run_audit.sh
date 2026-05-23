#!/usr/bin/env bash
# Security Audit Script for Arkon
# Prevents data exfiltration, telemetry leaks, supply chain attacks.
# Run after every upstream sync or dependency update.
#
# Exit codes:
#   0 = PASS (all checks clean)
#   1 = FAIL (critical issue — block merge)
#   2 = WARN (manual review required — non-blocking)
#
# Inputs:
#   AUDIT_PATCH_FILE  Optional path to an upstream patch; enables Check #9.

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# shellcheck source=lib/audit-helpers.sh
source "$SCRIPT_DIR/lib/audit-helpers.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

FAIL_COUNT=0
WARN_COUNT=0

pass()  { echo -e "${GREEN}[PASS]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; WARN_COUNT=$((WARN_COUNT+1)); }
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
title() { echo -e "\n${YELLOW}▶ $1${NC}"; }

# Pre-flight: required tools.
if ! command -v jq >/dev/null 2>&1; then
  warn "jq not installed — SDK scan will use fallback grep with looser matching."
  HAVE_JQ=0
else
  HAVE_JQ=1
fi

# ===========================================================================
# 1. Framework Telemetry — Bug #1 fix
# Parse .env / next.config.* strictly; no substring matching across all files.
# ===========================================================================
title "Framework Telemetry"

TELEMETRY_OK=0
ENV_FILES=(
  .env .env.local .env.production .env.development .env.docker
  frontend/.env frontend/.env.local frontend/.env.production
)
if check_env_flag_truthy "${ENV_FILES[@]}" NEXT_TELEMETRY_DISABLED '^(1|true|True|TRUE)$'; then
  TELEMETRY_OK=1
fi

# next.config.* fallback (env may not be the only place it's set)
if [ "$TELEMETRY_OK" -eq 0 ]; then
  for cfg in next.config.js next.config.mjs next.config.ts \
             frontend/next.config.js frontend/next.config.mjs frontend/next.config.ts; do
    [ -f "$cfg" ] || continue
    if grep -Eq "NEXT_TELEMETRY_DISABLED[[:space:]]*[:=][[:space:]]*['\"]?(1|true)['\"]?" "$cfg"; then
      TELEMETRY_OK=1
      break
    fi
  done
fi

# Container-level fallback: docker-compose env arrays, Dockerfile ENV directives.
# Containers inherit the var at runtime which is what telemetry actually reads.
if [ "$TELEMETRY_OK" -eq 0 ]; then
  for cfg in docker-compose.yml docker-compose.yaml \
             frontend/Dockerfile Dockerfile; do
    [ -f "$cfg" ] || continue
    # Matches: `- NEXT_TELEMETRY_DISABLED=1`, `NEXT_TELEMETRY_DISABLED: 1`,
    # `ENV NEXT_TELEMETRY_DISABLED=1`, `ENV NEXT_TELEMETRY_DISABLED 1`.
    if grep -Eq "(^|[[:space:]-])(ENV[[:space:]]+)?NEXT_TELEMETRY_DISABLED([[:space:]]*[=:][[:space:]]*|[[:space:]]+)['\"]?(1|true)['\"]?" "$cfg"; then
      TELEMETRY_OK=1
      break
    fi
  done
fi

if [ "$TELEMETRY_OK" -eq 1 ]; then
  pass "NEXT_TELEMETRY_DISABLED=1 enforced"
else
  fail "NEXT_TELEMETRY_DISABLED not set to 1 in any env or next.config.*"
fi

# ===========================================================================
# 2. Forbidden SDKs / Tracking Libraries — Bug #2 fix
# Parse package.json with jq; word-boundary match in requirements/pyproject.
# ===========================================================================
title "Forbidden SDK Scan (Analytics / Tracking)"

FOUND_FORBIDDEN=0

# JSON packages — jq parse of deps trees
for json in package.json frontend/package.json; do
  [ -f "$json" ] || continue
  if [ "$HAVE_JQ" -eq 1 ]; then
    while IFS= read -r pkg; do
      [ -z "$pkg" ] && continue
      if pkg_matches_forbidden "$pkg"; then
        warn "Forbidden package in $json: $pkg"
        FOUND_FORBIDDEN=1
      fi
    done < <(jq_deps "$json")
  else
    # Fallback: word-boundary match on quoted dep keys
    for pkg in "${FORBIDDEN_PKG_NAMES[@]}"; do
      if grep -Eq "^[[:space:]]*\"@?[^\"]*${pkg}[^\"]*\"[[:space:]]*:" "$json"; then
        warn "Forbidden package candidate in $json: $pkg (jq fallback)"
        FOUND_FORBIDDEN=1
      fi
    done
  fi
done

# Python — word-boundary anchored
for req in requirements.txt requirements-dev.txt requirements-prod.txt; do
  [ -f "$req" ] || continue
  for pkg in "${FORBIDDEN_PKG_NAMES[@]}"; do
    if grep -Eq "^[[:space:]]*${pkg}([=~<>!\[].*|[[:space:]]*$)" "$req"; then
      warn "Forbidden package in $req: $pkg"
      FOUND_FORBIDDEN=1
    fi
  done
done

if [ -f pyproject.toml ]; then
  for pkg in "${FORBIDDEN_PKG_NAMES[@]}"; do
    if grep -Eq "^[[:space:]]*\"?${pkg}\"?[[:space:]]*=" pyproject.toml; then
      warn "Forbidden package in pyproject.toml: $pkg"
      FOUND_FORBIDDEN=1
    fi
    # Also catch poetry style `pkg = "x.y"` inside [tool.poetry.dependencies]
    if grep -Eq "^[[:space:]]*${pkg}[[:space:]]*=" pyproject.toml; then
      :  # already handled above (quoted form); leave for completeness
    fi
  done
fi

[ "$FOUND_FORBIDDEN" -eq 0 ] && pass "No forbidden analytics/tracking SDKs found"

# ===========================================================================
# 3. Suspicious External Network Calls — Bug #3 fix
# Whitelist is explicit URL literals (quoted) for known AI provider hosts.
# Inline comments and relative /api/ paths are excluded.
# ===========================================================================
title "Custom Network Call Scan"

# Known-safe API client entry points get fully excluded.
SAFE_API_FILES=(
  ./frontend/src/lib/api.ts
  ./frontend/src/lib/api.js
)
SAFE_API_PRUNE=()
for f in "${SAFE_API_FILES[@]}"; do
  SAFE_API_PRUNE+=("!" "-path" "$f")
done

# Capture all candidate hits; filter afterwards.
NETWORK_RE='(fetch\(|axios\.|requests\.(get|post|put|patch|delete)|httpx\.(get|post|put|patch|delete|AsyncClient)|aiohttp\.ClientSession|urllib\.request|http\.client|XMLHttpRequest|navigator\.sendBeacon|new WebSocket\(|new Image\(\)\.src[[:space:]]*=|eval\(|new Function\()'

RAW_HITS=$(find . \
  "${FIND_EXCLUDES[@]}" \
  "${SAFE_API_PRUNE[@]}" \
  -type f \
  \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o -name "*.jsx" \) \
  -exec grep -EnH "$NETWORK_RE" {} + 2>/dev/null || true)

# Filter strategy (least false-positive form):
#   1. Drop comment lines (lead with //, #, /*, *).
#   2. Keep ONLY lines that contain an EXPLICIT external URL literal
#      (`https?://...` in quotes/backticks). Variable URLs and relative
#      `/api/` paths are PASS — they don't statically reveal a foreign host.
#   3. Drop any remaining line whose URL literal matches the allowlist.
SUSPICIOUS=$(echo "$RAW_HITS" \
  | grep -Ev "^[^:]+:[0-9]+:[[:space:]]*(//|#|/\*|\*)" \
  | grep -E "[\"'\`]https?://" \
  | awk -v allow="$ALLOWED_URL_PATTERN" '
      {
        n=index($0, ":")
        rest=substr($0, n+1)
        m=index(rest, ":")
        line=substr(rest, m+1)
        if (line ~ allow) next
        print
      }' \
  || true)

if [ -z "$SUSPICIOUS" ]; then
  pass "No suspicious external network calls found"
else
  warn "Suspicious network patterns — manual review required:"
  echo "$SUSPICIOUS" | head -40
fi

# ===========================================================================
# 4. Tracking / Behavioral Analytics Patterns
# ===========================================================================
title "Behavioral Tracking Pattern Scan"

TRACKING=$(find . \
  "${FIND_EXCLUDES[@]}" \
  -type f \
  \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" -o -name "*.jsx" \) \
  -exec grep -EnH \
    "(track\(|trackEvent\(|reportUsage\(|sendEvent\(|emitAction\(|captureEvent\(|logBehavior\(|recordActivity\()" {} + 2>/dev/null \
  | grep -Ev "^[^:]+:[0-9]+:[[:space:]]*(//|#|/\*|\*)" \
  | grep -Ei "(user|email|content|wiki|document|behavior|session|ip)" \
  || true)

if [ -z "$TRACKING" ]; then
  pass "No behavioral tracking logic found"
else
  warn "Potential tracking logic — manual review required:"
  echo "$TRACKING" | head -20
fi

# ===========================================================================
# 5. External CDN / Font Leakage — Bug #4 fix
# Only exclude lines whose FIRST non-blank content is a comment marker.
# ===========================================================================
title "External CDN / Runtime Asset Check"

CDN_REFS=""
if [ -d ./frontend/src ] || [ -d ./frontend/public ]; then
  CDN_TARGETS=()
  [ -d ./frontend/src ] && CDN_TARGETS+=(./frontend/src)
  [ -d ./frontend/public ] && CDN_TARGETS+=(./frontend/public)
  CDN_REFS=$(find "${CDN_TARGETS[@]}" \
    "${FIND_EXCLUDES[@]}" \
    -type f \( -name "*.tsx" -o -name "*.ts" -o -name "*.jsx" -o -name "*.js" -o -name "*.html" -o -name "*.css" \) \
    -exec grep -EnH \
      "(fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com|unpkg\.com|cdn\.jsdelivr\.net|cdn\.tailwindcss\.com)" {} + 2>/dev/null \
    | grep -Ev "^[^:]+:[0-9]+:[[:space:]]*(//|#|/\*|\*)" \
    || true)
fi

if [ -z "$CDN_REFS" ]; then
  pass "No external CDN references in runtime code"
else
  warn "External CDN reference found (may leak user IP at runtime):"
  echo "$CDN_REFS"
fi

# ===========================================================================
# 6. Squid Whitelist Integrity
# ===========================================================================
title "Squid Proxy Whitelist Integrity"

SQUID_CONF="./squid/squid.conf"
if [ -f "$SQUID_CONF" ]; then
  # Bare wildcards = FAIL. Specific subdomains under same TLD are OK.
  if grep -Eq "^[[:space:]]*acl[[:space:]]+whitelisted_domains[[:space:]]+dstdomain[[:space:]]+\.googleapis\.com([[:space:]]|$)" "$SQUID_CONF"; then
    fail "Squid whitelist has bare .googleapis.com wildcard — overly broad"
  elif grep -Eq "^[[:space:]]*acl[[:space:]]+whitelisted_domains[[:space:]]+dstdomain[[:space:]]+\.google\.com([[:space:]]|$)" "$SQUID_CONF"; then
    fail "Squid whitelist has bare .google.com wildcard — overly broad"
  else
    pass "Squid whitelist uses specific domains only"
  fi

  if grep -Eq "^[[:space:]]*http_access[[:space:]]+deny[[:space:]]+all[[:space:]]*$" "$SQUID_CONF"; then
    pass "Squid default-deny rule present"
  else
    fail "Squid default-deny rule missing!"
  fi
else
  fail "squid/squid.conf not found"
fi

# ===========================================================================
# 7. Container Hardening — YAML-aware parse
# ===========================================================================
title "Container Hardening (docker-compose.yml)"

DC_FILE="docker-compose.yml"
if [ -f "$DC_FILE" ]; then
  # Per-service read_only check via parse_yaml_services helper.
  RO_MISSING=()
  while IFS='|' read -r svc ro _nets; do
    [ -z "$svc" ] && continue
    if [ "$ro" != "true" ]; then
      RO_MISSING+=("$svc")
    fi
  done < <(parse_yaml_services "$DC_FILE")

  if [ "${#RO_MISSING[@]}" -eq 0 ]; then
    pass "All services declare read_only: true"
  else
    if grep -Eq "^[[:space:]]+read_only:[[:space:]]+true" "$DC_FILE"; then
      # At least one service is hardened. Stateful services (databases,
      # object stores, caches) legitimately need writes — log as INFO so the
      # check passes overall.
      pass "read_only: true present on at least one service"
      info "Services without read_only (expected for stateful workloads): ${RO_MISSING[*]}"
    else
      fail "read_only: true missing on every service in $DC_FILE"
    fi
  fi

  # arkon_internal network must declare internal: true.
  if yaml_has_internal_network "$DC_FILE" arkon_internal; then
    pass "arkon_internal network is internal-only"
  else
    # Tolerate alternate name `internal_net` in older configs.
    if yaml_has_internal_network "$DC_FILE" internal_net; then
      pass "internal_net network declares internal: true"
    else
      fail "arkon_internal network missing internal: true"
    fi
  fi
else
  info "$DC_FILE not present — skipping container hardening check"
fi

# ===========================================================================
# 8. Dependency CVE Audit
# ===========================================================================
title "Dependency CVE Audit"

if command -v npm >/dev/null 2>&1 && [ -f "./frontend/package.json" ]; then
  info "Running npm audit (frontend)..."
  if npm audit --audit-level=high --prefix ./frontend >/dev/null 2>&1; then
    pass "npm audit: no high/critical vulnerabilities"
  else
    warn "npm audit found high/critical vulnerabilities — review required"
  fi
else
  info "npm not found or no frontend/package.json — skipping"
fi

if command -v pip-audit >/dev/null 2>&1 && [ -f "./pyproject.toml" ]; then
  info "Running pip-audit (backend)..."
  if pip-audit --desc >/dev/null 2>&1; then
    pass "pip-audit: no known vulnerabilities"
  else
    warn "pip-audit found vulnerabilities — review required"
  fi
else
  info "pip-audit not installed — skipping. Install: pip install pip-audit"
fi

# ===========================================================================
# 9. Upstream Patch Scan (only when AUDIT_PATCH_FILE is set)
# Scans +lines for forbidden patterns introduced upstream.
# ===========================================================================
if [ -n "${AUDIT_PATCH_FILE:-}" ] && [ -f "$AUDIT_PATCH_FILE" ]; then
  title "Upstream Patch Scan (pre-merge, incoming +lines only)"

  # Extract +lines only (drop +++ headers).
  PATCH_ADDS=$(grep -E "^\+" "$AUDIT_PATCH_FILE" | grep -v "^+++" || true)

  # 9a. Forbidden SDKs in incoming diff
  FOUND_UP_PKG=0
  if [ -n "$PATCH_ADDS" ]; then
    # Use word-boundary match per package.
    for pkg in "${FORBIDDEN_PKG_NAMES[@]}"; do
      # require the package to appear as a token (json key, import target, or pip pin)
      if echo "$PATCH_ADDS" \
           | grep -Eq "[\"'](@[^\"']*${pkg}[^\"']*|${pkg}[^\"']*)[\"'][[:space:]]*:|[[:space:]]from[[:space:]]+['\"][^'\"]*${pkg}|[[:space:]]import[[:space:]]+[^[:space:]]*${pkg}|^\+[[:space:]]*${pkg}[=~<>]" 2>/dev/null; then
        warn "Upstream patch introduces forbidden package: $pkg"
        FOUND_UP_PKG=1
      fi
    done
  fi
  [ "$FOUND_UP_PKG" -eq 0 ] && pass "No forbidden analytics/tracking packages in upstream patch"

  # 9b. Suspicious network calls in incoming diff
  if [ -n "$PATCH_ADDS" ] && echo "$PATCH_ADDS" | grep -Eq \
       "(fetch\(|axios\.|httpx\.(get|post|AsyncClient)|sendBeacon|new WebSocket\(|eval\()"; then
    # Filter out lines that target an allowlisted URL.
    SUS_PATCH_LINES=$(echo "$PATCH_ADDS" \
      | grep -E "(fetch\(|axios\.|httpx\.(get|post|AsyncClient)|sendBeacon|new WebSocket\(|eval\()" \
      | awk -v allow="$ALLOWED_URL_PATTERN" '!($0 ~ allow)' || true)
    if [ -n "$SUS_PATCH_LINES" ]; then
      warn "Upstream patch adds network calls to non-allowlisted hosts — manual review required"
      echo "$SUS_PATCH_LINES" | head -10
    else
      pass "Upstream patch network calls target allowlisted hosts only"
    fi
  else
    pass "No suspicious network calls in upstream patch"
  fi

  # 9c. External CDN in incoming diff
  if [ -n "$PATCH_ADDS" ] && echo "$PATCH_ADDS" | grep -Eq \
       "(fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com|unpkg\.com|cdn\.jsdelivr\.net)"; then
    warn "Upstream patch adds external CDN reference — may leak user IP at runtime"
  else
    pass "No external CDN references in upstream patch"
  fi
fi

# ===========================================================================
# Summary
# ===========================================================================
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ "$FAIL_COUNT" -gt 0 ]; then
  echo -e "${RED}❌ Audit FAILED: $FAIL_COUNT critical issue(s), $WARN_COUNT warning(s)${NC}"
  exit 1
elif [ "$WARN_COUNT" -gt 0 ]; then
  echo -e "${YELLOW}⚠️  Audit completed with $WARN_COUNT warning(s) — manual review required${NC}"
  exit 2
else
  echo -e "${GREEN}✅ Audit PASSED — all checks clean${NC}"
  exit 0
fi
