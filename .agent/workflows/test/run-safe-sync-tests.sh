#!/usr/bin/env bash
# run-safe-sync-tests.sh
# Integration tests for safe_sync.sh hard gate.
# Uses a temporary git repo + fake upstream so we don't touch real remotes.

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
SAFE_SYNC="$REPO_ROOT/.agent/workflows/safe_sync.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

PASS=0
FAIL=0

assert_exit() {
  local label="$1" expected="$2" actual="$3" output="$4"
  if [ "$actual" -eq "$expected" ]; then
    echo -e "${GREEN}✅ $label${NC}: exit $actual (expected $expected)"
    PASS=$((PASS+1))
  else
    echo -e "${RED}❌ $label${NC}: exit $actual (expected $expected)"
    echo "$output" | tail -10 | sed 's/^/    /'
    FAIL=$((FAIL+1))
  fi
}

TMP=$(mktemp -d -t safe-sync-test.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

# Build fake upstream + downstream repos.
UPSTREAM_DIR="$TMP/upstream"
LOCAL_DIR="$TMP/local"

(
  set -e
  git init -q -b main "$UPSTREAM_DIR"
  cd "$UPSTREAM_DIR"
  git config user.email test@example.com
  git config user.name test
  echo "v1" > file.txt
  git add file.txt
  git commit -q -m "init"
  echo "v2" > file.txt
  git commit -qa -m "v2 upstream"
)

(
  set -e
  git clone -q -b main "$UPSTREAM_DIR" "$LOCAL_DIR" 2>/dev/null
  cd "$LOCAL_DIR"
  git config user.email test@example.com
  git config user.name test
  # Reset local to v1 so we have something to merge.
  git reset -q --hard HEAD~1
  # Treat the clone source as the "upstream" remote (mirrors the real layout).
  git remote rename origin upstream 2>/dev/null || true
  mkdir -p plans/reports .agent/workflows
  cp "$SAFE_SYNC" .agent/workflows/safe_sync.sh
  # Stub run_audit.sh so the legacy interactive path can resolve it.
  cat > .agent/workflows/run_audit.sh <<'STUB'
#!/usr/bin/env bash
echo "[stub] audit ok"
exit 0
STUB
  chmod +x .agent/workflows/run_audit.sh .agent/workflows/safe_sync.sh
)

# -- Test 1: --merge without any report MUST refuse with exit 1 --
output=$(cd "$LOCAL_DIR" && bash .agent/workflows/safe_sync.sh upstream main --merge 2>&1) || rc=$?
rc=${rc:-0}
assert_exit "gate refuses --merge with no report" 1 "$rc" "$output"
unset rc

# -- Test 2: --merge with WRONG sha report MUST still refuse --
WRONG_SHA="0000000000000000000000000000000000000000"
cat > "$LOCAL_DIR/plans/reports/sync-audit-260523-9999-wrong.md" <<EOF
---
upstream_sha: $WRONG_SHA
audit_status: PASS
---
report body
EOF
output=$(cd "$LOCAL_DIR" && bash .agent/workflows/safe_sync.sh upstream main --merge 2>&1) || rc=$?
rc=${rc:-0}
assert_exit "gate refuses --merge with mismatched sha" 1 "$rc" "$output"
unset rc

# -- Test 3: --merge with matching sha but WARN status MUST refuse --
UPSTREAM_SHA=$(cd "$LOCAL_DIR" && git ls-remote upstream main | awk '{print $1}')
cat > "$LOCAL_DIR/plans/reports/sync-audit-260523-9998-warn.md" <<EOF
---
upstream_sha: $UPSTREAM_SHA
audit_status: WARN
---
warn body
EOF
output=$(cd "$LOCAL_DIR" && bash .agent/workflows/safe_sync.sh upstream main --merge 2>&1) || rc=$?
rc=${rc:-0}
assert_exit "gate refuses --merge with audit_status=WARN" 1 "$rc" "$output"
unset rc

# -- Test 4: --merge with matching sha + PASS MUST proceed (exit 0) --
rm -f "$LOCAL_DIR/plans/reports/sync-audit-260523-9998-warn.md"
cat > "$LOCAL_DIR/plans/reports/sync-audit-260523-9997-pass.md" <<EOF
---
upstream_sha: $UPSTREAM_SHA
audit_status: PASS
---
pass body
EOF
output=$(cd "$LOCAL_DIR" && bash .agent/workflows/safe_sync.sh upstream main --merge 2>&1) || rc=$?
rc=${rc:-0}
assert_exit "gate allows --merge with matching PASS report" 0 "$rc" "$output"
unset rc

# -- Test 5: dry-run mode archives without merging --
(cd "$LOCAL_DIR" && git reset -q --hard HEAD~1) >/dev/null 2>&1 || true
output=$(cd "$LOCAL_DIR" && SYNC_MODE=dryrun bash .agent/workflows/safe_sync.sh upstream main 2>&1) || rc=$?
rc=${rc:-0}
assert_exit "dry-run exits 0 and archives patch" 0 "$rc" "$output"
unset rc

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " safe_sync tests: $PASS passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ]
