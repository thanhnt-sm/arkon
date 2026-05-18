#!/bin/bash
# Security Audit Script for Arkon
# Prevents data exfiltration, telemetry leaks, and supply chain attacks.
# Run after every upstream sync or dependency update.

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

FAIL_COUNT=0
WARN_COUNT=0

pass()  { echo -e "${GREEN}[PASS]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn()  { echo -e "${RED}[WARN]${NC} $1"; WARN_COUNT=$((WARN_COUNT+1)); }
info()  { echo -e "${CYAN}[INFO]${NC} $1"; }
title() { echo -e "\n${YELLOW}▶ $1${NC}"; }

# ---------------------------------------------------------------------------
# 1. Framework Telemetry
# ---------------------------------------------------------------------------
title "Framework Telemetry"

grep -r "NEXT_TELEMETRY_DISABLED" . --exclude-dir=node_modules 2>/dev/null | grep -q "=1" \
  && pass "NEXT_TELEMETRY_DISABLED=1 enforced" \
  || fail "NEXT_TELEMETRY_DISABLED not set to 1"

# ---------------------------------------------------------------------------
# 2. Forbidden SDKs / Tracking Libraries
# ---------------------------------------------------------------------------
title "Forbidden SDK Scan (Analytics / Tracking)"

FORBIDDEN_PKGS=(
  "posthog" "mixpanel" "amplitude" "segment" "fullstory"
  "hotjar" "logrocket" "datadog" "sentry" "newrelic"
  "google-analytics" "gtag" "heap" "pendo" "intercom"
)

FOUND_FORBIDDEN=0
for pkg in "${FORBIDDEN_PKGS[@]}"; do
  if grep -r "$pkg" . \
       --exclude-dir=node_modules --exclude-dir=.git \
       --include="*.json" --include="*.toml" --include="*.txt" \
       -l 2>/dev/null | grep -q .; then
    warn "Forbidden package detected: $pkg"
    FOUND_FORBIDDEN=1
  fi
done
[ $FOUND_FORBIDDEN -eq 0 ] && pass "No forbidden analytics/tracking SDKs found"

# ---------------------------------------------------------------------------
# 3. Suspicious External Network Calls (Custom Code)
# ---------------------------------------------------------------------------
title "Custom Network Call Scan"

# Excludes: our known-safe API client entry points
EXCLUDE_FILES=(
  "./frontend/src/lib/api.ts"
  "./frontend/src/lib/api.js"
)
EXCLUDE_ARGS=()
for f in "${EXCLUDE_FILES[@]}"; do
  EXCLUDE_ARGS+=("!" "-path" "$f")
done

SUSPICIOUS=$(find . \
  "${EXCLUDE_ARGS[@]}" \
  -not -path '*/.*' \
  -not -path './node_modules/*' \
  -not -path './frontend/node_modules/*' \
  -not -path './.agent/*' \
  -type f \
  \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \) \
  -exec grep -EnH \
    "(fetch\(|axios\.|requests\.(get|post|put|patch|delete)\
|httpx\.(get|post|put|patch|delete|AsyncClient)\
|aiohttp\.ClientSession\
|urllib\.request\
|http\.client\
|XMLHttpRequest\
|navigator\.sendBeacon\
|new WebSocket\(|new Image\(\)\.src\s*=\
|eval\(|new Function\()" {} + 2>/dev/null \
  | grep -Ev "(#.*|//.*|localhost|127\.0\.0\.1|arkon_internal\
|/api/|openai\.com|anthropic\.com|generativelanguage\.googleapis\.com)" \
  || true)

if [ -z "$SUSPICIOUS" ]; then
  pass "No suspicious external network calls found"
else
  warn "Suspicious network patterns — manual review required:"
  echo "$SUSPICIOUS" | head -40
fi

# ---------------------------------------------------------------------------
# 4. Tracking / Behavioral Analytics Patterns
# ---------------------------------------------------------------------------
title "Behavioral Tracking Pattern Scan"

TRACKING=$(find . \
  -not -path '*/.*' \
  -not -path './node_modules/*' \
  -not -path './frontend/node_modules/*' \
  -not -path './.agent/*' \
  -type f \
  \( -name "*.py" -o -name "*.js" -o -name "*.ts" -o -name "*.tsx" \) \
  -exec grep -EnH \
    "(track\(|trackEvent\(|reportUsage\(|sendEvent\(|emitAction\(\
|captureEvent\(|logBehavior\(|recordActivity\()" {} + 2>/dev/null \
  | grep -Ei "(user|email|content|wiki|document|behavior|session|ip)" \
  || true)

if [ -z "$TRACKING" ]; then
  pass "No behavioral tracking logic found"
else
  warn "Potential tracking logic — manual review required:"
  echo "$TRACKING" | head -20
fi

# ---------------------------------------------------------------------------
# 5. External CDN / Font Leakage (Runtime)
# ---------------------------------------------------------------------------
title "External CDN / Runtime Asset Check"

CDN_REFS=$(find ./frontend/src ./frontend/public \
  -not -path '*/node_modules/*' \
  -type f \( -name "*.tsx" -o -name "*.ts" -o -name "*.html" -o -name "*.css" \) \
  -exec grep -EnH \
    "(fonts\.googleapis\.com|fonts\.gstatic\.com|cdnjs\.cloudflare\.com\
|unpkg\.com|cdn\.jsdelivr\.net|cdn\.tailwindcss\.com)" {} + 2>/dev/null \
  | grep -v "// " \
  | grep -v "#" \
  || true)

if [ -z "$CDN_REFS" ]; then
  pass "No external CDN references in runtime code"
else
  warn "External CDN reference found (may leak user IP at runtime):"
  echo "$CDN_REFS"
fi

# ---------------------------------------------------------------------------
# 6. Squid Whitelist Integrity
# ---------------------------------------------------------------------------
title "Squid Proxy Whitelist Integrity"

SQUID_CONF="./squid/squid.conf"
if [ -f "$SQUID_CONF" ]; then
  # Must NOT contain broad wildcards
  if grep -q "\.googleapis\.com$" "$SQUID_CONF" 2>/dev/null \
     && ! grep -q "generativelanguage\.googleapis\.com" "$SQUID_CONF" 2>/dev/null; then
    fail "Squid whitelist has .googleapis.com wildcard — overly broad"
  elif grep -Eq "^\s*acl whitelisted_domains dstdomain \.google\.com" "$SQUID_CONF" 2>/dev/null; then
    fail "Squid whitelist has .google.com wildcard — overly broad"
  else
    pass "Squid whitelist uses specific domains only"
  fi

  # Must have deny all at end
  grep -q "http_access deny all" "$SQUID_CONF" \
    && pass "Squid default-deny rule present" \
    || fail "Squid default-deny rule missing!"
else
  fail "squid/squid.conf not found"
fi

# ---------------------------------------------------------------------------
# 7. Container Hardening
# ---------------------------------------------------------------------------
title "Container Hardening (docker-compose.yml)"

grep -q "read_only: true" docker-compose.yml \
  && pass "read_only containers configured" \
  || fail "read_only: true missing in docker-compose.yml"

grep -q "internal: true" docker-compose.yml \
  && pass "arkon_internal network is internal-only" \
  || fail "arkon_internal network missing internal: true"

# ---------------------------------------------------------------------------
# 8. Dependency Audit (Known CVEs)
# ---------------------------------------------------------------------------
title "Dependency CVE Audit"

if command -v npm &>/dev/null && [ -f "./frontend/package.json" ]; then
  info "Running npm audit (frontend)..."
  npm audit --audit-level=high --prefix ./frontend 2>&1 | tail -5 \
    && pass "npm audit: no high/critical vulnerabilities" \
    || warn "npm audit found high/critical vulnerabilities — review required"
else
  info "npm not found or no frontend/package.json — skipping"
fi

if command -v pip-audit &>/dev/null && [ -f "./pyproject.toml" ]; then
  info "Running pip-audit (backend)..."
  pip-audit --desc 2>&1 | tail -5 \
    && pass "pip-audit: no known vulnerabilities" \
    || warn "pip-audit found vulnerabilities — review required"
else
  info "pip-audit not installed — skipping. Install: pip install pip-audit"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAIL_COUNT -gt 0 ]; then
  echo -e "${RED}❌ Audit FAILED: $FAIL_COUNT critical issue(s), $WARN_COUNT warning(s)${NC}"
  exit 1
elif [ $WARN_COUNT -gt 0 ]; then
  echo -e "${YELLOW}⚠️  Audit completed with $WARN_COUNT warning(s) — manual review required${NC}"
  exit 2
else
  echo -e "${GREEN}✅ Audit PASSED — all checks clean${NC}"
  exit 0
fi
