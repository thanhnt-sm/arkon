#!/usr/bin/env bash
# append_index.sh
# Append a single forensic-ledger row to .agent/sync_history/INDEX.md.
# Initializes the file with a header if missing.
#
# Usage:
#   append_index.sh <iso-timestamp> <upstream-sha> <patch-file> <status> <report-file> [action]
#
# Notes:
#   - action defaults to "dry-run"; safe_sync.sh --merge sets it to "merged".
#   - Uses an atomic temp + mv pattern; idempotent w.r.t. header initialization.

set -euo pipefail

if [ "$#" -lt 5 ]; then
  echo "Usage: $0 <iso-timestamp> <upstream-sha> <patch-file> <status> <report-file> [action]" >&2
  exit 1
fi

TIMESTAMP="$1"
SHA="$2"
PATCH="$3"
STATUS="$4"
REPORT="$5"
ACTION="${6:-dry-run}"

REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." && pwd )"
INDEX="$REPO_ROOT/.agent/sync_history/INDEX.md"
mkdir -p "$(dirname "$INDEX")"

if [ ! -f "$INDEX" ]; then
  cat > "$INDEX" <<'EOF'
# Sync History Index

Forensic ledger — one row per `safe_sync.sh` invocation (dry-run + merged).

| Timestamp | Upstream SHA | Patch File | Audit | Report | Action |
|-----------|--------------|------------|-------|--------|--------|
EOF
fi

SHORT_SHA="${SHA:0:12}"
PATCH_NAME=$(basename "$PATCH")
REPORT_NAME=""
[ -n "$REPORT" ] && REPORT_NAME=$(basename "$REPORT")

ROW="| $TIMESTAMP | $SHORT_SHA | $PATCH_NAME | $STATUS | $REPORT_NAME | $ACTION |"

TMP=$(mktemp -t arkon-index.XXXXXX)
cat "$INDEX" > "$TMP"
echo "$ROW" >> "$TMP"
mv "$TMP" "$INDEX"

echo "[index] appended row to $INDEX"
