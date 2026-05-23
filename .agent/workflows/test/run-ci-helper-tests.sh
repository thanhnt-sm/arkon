#!/usr/bin/env bash
# run-ci-helper-tests.sh
# Integration tests for Phase 3 CI helpers:
#   - generate_report.sh (frontmatter parseable by safe_sync gate)
#   - update_metrics.sh (atomic counter increment)
#   - append_index.sh (forensic ledger row)
# Bash 3.2 compatible. Uses ephemeral repo in $TMPDIR.

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
GEN_REPORT="$REPO_ROOT/.agent/workflows/generate_report.sh"
UPD_METRICS="$REPO_ROOT/.agent/workflows/update_metrics.sh"
APP_INDEX="$REPO_ROOT/.agent/workflows/append_index.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; NC='\033[0m'
PASS=0; FAIL=0
ok() { echo -e "${GREEN}✅ $*${NC}"; PASS=$((PASS+1)); }
no() { echo -e "${RED}❌ $*${NC}"; FAIL=$((FAIL+1)); }

TMP=$(mktemp -d -t arkon-ci-helpers.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

# Ephemeral repo with an upstream/main ref so generate_report can resolve it.
UPSTREAM_DIR="$TMP/upstream"
LOCAL_DIR="$TMP/local"
git init -q -b main "$UPSTREAM_DIR"
(
  cd "$UPSTREAM_DIR"
  git config user.email t@t; git config user.name t
  echo "a" > a.txt && git add a.txt && git commit -q -m init
  echo "b" >> a.txt && git commit -qam advance
)
git clone -q "$UPSTREAM_DIR" "$LOCAL_DIR"
(
  cd "$LOCAL_DIR"
  git config user.email t@t; git config user.name t
  git remote rename origin upstream
  git fetch -q upstream main
  git reset -q --hard HEAD~0  # stay at the tip; we only need upstream/main ref
)

cd "$LOCAL_DIR"

# ─── 1. generate_report.sh writes parseable frontmatter ─────────────────
cat > "$TMP/audit.log" <<'EOF'
▶ Framework Telemetry
[PASS] NEXT_TELEMETRY_DISABLED=1 enforced

▶ Forbidden SDK Scan (Analytics / Tracking)
[PASS] No forbidden analytics/tracking SDKs found
✅ Audit PASSED — all checks clean
EOF
echo "[]" > "$TMP/conflicts.json"
# Need a patch file pointer (just any existing file).
touch "$TMP/fake.patch"

bash "$GEN_REPORT" "$TMP/fake.patch" "$TMP/audit.log" "$TMP/conflicts.json" \
  "$TMP/report.md" >/dev/null 2>&1 || { no "generate_report exit non-zero"; }

if [ -f "$TMP/report.md" ]; then
  UPSTREAM_SHA=$(git rev-parse upstream/main)
  if grep -q "^upstream_sha: $UPSTREAM_SHA\$" "$TMP/report.md"; then
    ok "generate_report frontmatter has upstream_sha matching upstream/main"
  else
    no "frontmatter upstream_sha mismatch"
  fi
  if grep -q "^audit_status: PASS\$" "$TMP/report.md"; then
    ok "generate_report sets audit_status=PASS from log"
  else
    no "audit_status not classified as PASS"
  fi
else
  no "report file not created"
fi

# ─── 2. generate_report classifies FAIL/WARN correctly ──────────────────
cat > "$TMP/audit-fail.log" <<'EOF'
▶ Squid Proxy Whitelist Integrity
[FAIL] Squid default-deny rule missing!
❌ Audit FAILED: 1 critical issue(s)
EOF
bash "$GEN_REPORT" "$TMP/fake.patch" "$TMP/audit-fail.log" "$TMP/conflicts.json" \
  "$TMP/report-fail.md" >/dev/null 2>&1
grep -q "^audit_status: FAIL\$" "$TMP/report-fail.md" \
  && ok "FAIL log → audit_status=FAIL" \
  || no "FAIL log classification wrong"

cat > "$TMP/audit-warn.log" <<'EOF'
▶ Dependency CVE Audit
[WARN] npm audit found high/critical vulnerabilities
⚠️  Audit completed with 1 warning(s)
EOF
bash "$GEN_REPORT" "$TMP/fake.patch" "$TMP/audit-warn.log" "$TMP/conflicts.json" \
  "$TMP/report-warn.md" >/dev/null 2>&1
grep -q "^audit_status: WARN\$" "$TMP/report-warn.md" \
  && ok "WARN log → audit_status=WARN" \
  || no "WARN log classification wrong"

# ─── 3. update_metrics.sh increments totals + per-check ─────────────────
export ARKON_AUDIT_NO_METRICS=1  # prevent regression-test inception
METRICS_DIR="$LOCAL_DIR/.agent/metrics"
mkdir -p "$METRICS_DIR"
rm -f "$METRICS_DIR/audit-counters.json"

unset ARKON_AUDIT_NO_METRICS  # only for *running* the metric updater here
bash "$UPD_METRICS" PASS "$TMP/audit.log" >/dev/null 2>&1 || true
bash "$UPD_METRICS" PASS "$TMP/audit.log" >/dev/null 2>&1 || true
bash "$UPD_METRICS" WARN "$TMP/audit-warn.log" >/dev/null 2>&1 || true

if [ -f "$METRICS_DIR/audit-counters.json" ]; then
  RUNS=$(jq -r '.totals.audit_runs' "$METRICS_DIR/audit-counters.json")
  PASSES=$(jq -r '.totals.pass' "$METRICS_DIR/audit-counters.json")
  WARNS=$(jq -r '.totals.warn' "$METRICS_DIR/audit-counters.json")
  if [ "$RUNS" = "3" ] && [ "$PASSES" = "2" ] && [ "$WARNS" = "1" ]; then
    ok "metrics totals correct (runs=3, pass=2, warn=1)"
  else
    no "metrics totals wrong: runs=$RUNS pass=$PASSES warn=$WARNS"
  fi
  if jq -e '.by_check | keys | length > 0' "$METRICS_DIR/audit-counters.json" >/dev/null 2>&1; then
    ok "metrics per-check section populated"
  else
    no "metrics per-check section empty"
  fi
else
  no "metrics file not created"
fi
export ARKON_AUDIT_NO_METRICS=1

# ─── 4. append_index.sh writes a row with header on first call ──────────
INDEX="$LOCAL_DIR/.agent/sync_history/INDEX.md"
rm -f "$INDEX"
bash "$APP_INDEX" "2026-05-23T12:00:00Z" "abcdef123456deadbeef" \
  ".agent/sync_history/20260523.patch" "PASS" \
  "plans/reports/sync-audit-260523.md" "merged" >/dev/null 2>&1 || true

if [ -f "$INDEX" ]; then
  grep -q "^# Sync History Index" "$INDEX" \
    && ok "append_index initialized header" \
    || no "header missing"
  grep -q "abcdef123456" "$INDEX" \
    && ok "append_index wrote short SHA" \
    || no "SHA row missing"
else
  no "INDEX.md not created"
fi

# ─── 5. append_index repeated calls append (no truncation) ──────────────
bash "$APP_INDEX" "2026-05-24T12:00:00Z" "fedcba654321cafefeed" \
  ".agent/sync_history/20260524.patch" "WARN" \
  "plans/reports/sync-audit-260524.md" "dry-run" >/dev/null 2>&1 || true

ROWS=$(grep -c "^| 2026-05-" "$INDEX" || echo 0)
[ "$ROWS" = "2" ] \
  && ok "append_index keeps prior rows (2 data rows total)" \
  || no "append_index lost rows: got $ROWS"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " CI helpers: $PASS passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ]
