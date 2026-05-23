#!/usr/bin/env bash
# run-audit-tests.sh
# Regression tests for run_audit.sh against synthetic patch fixtures.
# Verifies: (1) clean codebase baseline, (2) each fixture triggers expected exit.
# Bash 3.2 compatible — uses parallel arrays instead of associative arrays.

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
AUDIT_SCRIPT="$REPO_ROOT/.agent/workflows/run_audit.sh"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

PASS=0
FAIL=0

# Expected exit codes (see run_audit.sh header for semantics):
#   0 = PASS, 1 = FAIL (hard block), 2 = WARN (manual review)
# Adversarial fixtures all surface as WARN so CI gates without crashing on a
# single noisy upstream commit.
#
# Baseline policy: the current codebase has real (non-false-positive) WARNs
# such as outstanding npm audit CVEs. We accept exit 0 or 2 on baseline so the
# regression suite tracks correctness (no false positives, no false negatives)
# rather than CVE backlog hygiene.
FIXTURE_NAMES=(
  clean.patch
  posthog-added.patch
  evil-fetch.patch
  cdn-leak.patch
)
# "" means: must not exceed baseline severity (clean patch should not raise it).
# A number means: exact exit-code expected (adversarial fixture must trigger it).
FIXTURE_EXPECTED=(
  ""
  2
  2
  2
)

BASELINE_EXIT=0

run_case() {
  local label="$1" expected="$2" patch="${3:-}"
  local actual=0 cmd_output
  if [ -n "$patch" ]; then
    cmd_output=$(AUDIT_PATCH_FILE="$patch" bash "$AUDIT_SCRIPT" 2>&1) || actual=$?
  else
    cmd_output=$(bash "$AUDIT_SCRIPT" 2>&1) || actual=$?
  fi
  local ok=0
  if [ -z "$expected" ]; then
    # Clean fixture: must NOT add severity beyond baseline.
    # FAIL (1) > WARN (2 in audit semantics) handled explicitly.
    if [ "$actual" -eq "$BASELINE_EXIT" ]; then ok=1; fi
    # Also accept exit 0 if baseline was 2 (improvement, not regression).
    if [ "$BASELINE_EXIT" -eq 2 ] && [ "$actual" -eq 0 ]; then ok=1; fi
    local expdesc="≤ baseline ($BASELINE_EXIT)"
  else
    if [ "$actual" -eq "$expected" ]; then ok=1; fi
    local expdesc="exit $expected"
  fi
  if [ "$ok" -eq 1 ]; then
    echo -e "${GREEN}✅ $label${NC}: exit $actual ($expdesc)"
    PASS=$((PASS+1))
  else
    echo -e "${RED}❌ $label${NC}: exit $actual ($expdesc)"
    echo "$cmd_output" | tail -20 | sed 's/^/    /'
    FAIL=$((FAIL+1))
  fi
}

run_baseline() {
  local label="baseline (no patch)"
  local actual=0 cmd_output
  cmd_output=$(bash "$AUDIT_SCRIPT" 2>&1) || actual=$?
  BASELINE_EXIT="$actual"
  # Exit 1 means a check FAILed — that's a regression we MUST catch.
  if [ "$actual" -eq 0 ] || [ "$actual" -eq 2 ]; then
    echo -e "${GREEN}✅ $label${NC}: exit $actual (acceptable: 0 PASS or 2 WARN)"
    PASS=$((PASS+1))
  else
    echo -e "${RED}❌ $label${NC}: exit $actual (expected 0 or 2 — got FAIL)"
    echo "$cmd_output" | tail -20 | sed 's/^/    /'
    FAIL=$((FAIL+1))
  fi
}

cd "$REPO_ROOT"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Regression: run_audit.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

run_baseline

i=0
while [ "$i" -lt "${#FIXTURE_NAMES[@]}" ]; do
  fixture="${FIXTURE_NAMES[$i]}"
  expected="${FIXTURE_EXPECTED[$i]}"
  patch_path="$FIXTURES_DIR/$fixture"
  if [ ! -f "$patch_path" ]; then
    echo -e "${YELLOW}⚠️  skip${NC}: fixture missing $patch_path"
  else
    run_case "fixture: $fixture" "$expected" "$patch_path"
  fi
  i=$((i+1))
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Tests: $PASS passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ]
