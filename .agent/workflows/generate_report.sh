#!/usr/bin/env bash
# generate_report.sh
# Produce a sync-audit report Markdown file with mandatory frontmatter so
# safe_sync.sh --merge can parse `upstream_sha` + `audit_status` and gate.
#
# Usage:
#   generate_report.sh <patch-file> <audit-log> <conflicts-json> <output-path>
#
# Inputs:
#   patch-file       Forensic patch path (`.agent/sync_history/*.patch`).
#   audit-log        run_audit.sh stdout/stderr captured to a file.
#   conflicts-json   Output of categorize_conflicts.sh.
#   output-path      Destination .md file (created/overwritten).
#
# Exit codes:
#   0 = report written
#   1 = bad args
#   2 = upstream ref not resolvable

set -euo pipefail

if [ "$#" -lt 4 ]; then
  echo "Usage: $0 <patch-file> <audit-log> <conflicts-json> <output-path>" >&2
  exit 1
fi

PATCH_FILE="$1"
AUDIT_LOG="$2"
CONFLICTS_JSON="$3"
OUTPUT="$4"

[ -f "$PATCH_FILE" ]    || { echo "❌ patch not found: $PATCH_FILE" >&2; exit 1; }
[ -f "$AUDIT_LOG" ]     || { echo "❌ audit log not found: $AUDIT_LOG" >&2; exit 1; }
[ -f "$CONFLICTS_JSON" ] || { echo "❌ conflicts not found: $CONFLICTS_JSON" >&2; exit 1; }

UPSTREAM_REF="${UPSTREAM_REF:-upstream/main}"

if ! UPSTREAM_SHA=$(git rev-parse "$UPSTREAM_REF" 2>/dev/null); then
  echo "❌ cannot resolve $UPSTREAM_REF" >&2
  exit 2
fi

TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
COMMITS_BEHIND=$(git rev-list HEAD.."$UPSTREAM_REF" --count 2>/dev/null || echo 0)
FILES_CHANGED=$(jq 'length' "$CONFLICTS_JSON" 2>/dev/null || echo 0)

# Classify audit log → PASS/WARN/FAIL.
# Look at the final summary line written by run_audit.sh.
if grep -q "Audit PASSED" "$AUDIT_LOG"; then
  STATUS="PASS"; EXIT_CODE=0
elif grep -q "Audit FAILED" "$AUDIT_LOG"; then
  STATUS="FAIL"; EXIT_CODE=1
else
  STATUS="WARN"; EXIT_CODE=2
fi

mkdir -p "$(dirname "$OUTPUT")"

# Build the file via heredoc; trailing dynamic sections appended after.
cat > "$OUTPUT" <<EOF
---
upstream_sha: $UPSTREAM_SHA
upstream_ref: $UPSTREAM_REF
audit_status: $STATUS
audit_exit_code: $EXIT_CODE
timestamp: $TIMESTAMP
commits_behind: $COMMITS_BEHIND
files_changed: $FILES_CHANGED
patch_file: $PATCH_FILE
generated_by: generate_report.sh
---

# Sync Audit Report — $TIMESTAMP

**Remote:** $UPSTREAM_REF | **Behind:** $COMMITS_BEHIND commits | **Files:** $FILES_CHANGED
**Status:** $STATUS (exit $EXIT_CODE)
**Patch:** \`$PATCH_FILE\`

## 1. Security Audit Results

\`\`\`
EOF

# Per-check lines (PASS/FAIL/WARN entries). Fall back to "(no results)" if log
# was empty or didn't follow the expected format.
if grep -qE "^\[(PASS|FAIL|WARN|INFO)\]" "$AUDIT_LOG"; then
  grep -E "^\[(PASS|FAIL|WARN|INFO)\]" "$AUDIT_LOG" >> "$OUTPUT"
else
  echo "(no [PASS]/[WARN]/[FAIL] lines found in audit log)" >> "$OUTPUT"
fi

cat >> "$OUTPUT" <<EOF
\`\`\`

## 2. Conflict Inventory

| File | Category | Local LOC | Upstream LOC | Local Commits |
|------|----------|-----------|--------------|---------------|
EOF

if [ "$(jq 'length' "$CONFLICTS_JSON")" -gt 0 ]; then
  jq -r '.[] | "| \(.file) | \(.category) | \(.local_loc) | \(.upstream_loc) | \(.local_commits) |"' \
    "$CONFLICTS_JSON" >> "$OUTPUT"
else
  echo "| _(no files changed)_ | | | | |" >> "$OUTPUT"
fi

# Category counts.
if [ "$FILES_CHANGED" -gt 0 ]; then
  cat >> "$OUTPUT" <<EOF

**Category counts:**

\`\`\`
$(jq -r 'group_by(.category) | map("\(.[0].category): \(length)") | join("\n")' "$CONFLICTS_JSON")
\`\`\`
EOF
fi

# Recommended path varies by status.
case "$STATUS" in
  PASS)
    REC="Audit clean. Proceed via preview:\n\`\`\`\nbash .agent/workflows/preview_merge.sh $CONFLICTS_JSON $UPSTREAM_REF\n\`\`\`\nThen \`bash .agent/workflows/safe_sync.sh upstream main --merge\` to apply (gate verifies this report)."
    ;;
  WARN)
    REC="Manual review required for WARN items above. After resolving, re-run the audit and regenerate this report."
    ;;
  FAIL)
    REC="**BLOCKED.** Fix FAIL items before any merge. \`safe_sync.sh --merge\` will refuse this report."
    ;;
esac

cat >> "$OUTPUT" <<EOF

## 3. Recommended Path

$(printf '%b' "$REC")

## 4. Decision Prompt

- **A)** \`bash .agent/workflows/preview_merge.sh $CONFLICTS_JSON $UPSTREAM_REF\` — create preview branch
- **B)** Manual hunk cherry-pick (per-file)
- **C)** Abort — no action

EOF

echo "✅ Report: $OUTPUT"
echo "   Status: $STATUS (exit $EXIT_CODE), upstream_sha: ${UPSTREAM_SHA:0:12}"
