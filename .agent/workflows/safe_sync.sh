#!/usr/bin/env bash
# ==============================================================================
# Upstream Sync Gateway (Safe Sync Workflow)
# Prevents blind git pull from upstream. Forces diff review + dependency alert.
# User must confirm before merge. Diff is archived (never deleted) for forensics.
# ==============================================================================

set -euo pipefail

REMOTE=${1:-upstream}
BRANCH=${2:-main}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HISTORY_DIR=".agent/sync_history"
PATCH_FILE="$HISTORY_DIR/${TIMESTAMP}_${REMOTE}_${BRANCH}.patch"

mkdir -p "$HISTORY_DIR"

if ! git remote | grep -q "^$REMOTE$"; then
    echo "❌ Remote '$REMOTE' not found. Add it: git remote add upstream <url>"
    exit 1
fi

echo "🔄 Fetching $REMOTE/$BRANCH..."
git fetch "$REMOTE" "$BRANCH"

LOCAL=$(git rev-parse @)
REMOTE_REF=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_REF" ]; then
    echo "✅ Already up to date with $REMOTE/$BRANCH."
    exit 0
fi

echo ""
echo "⚠️  Incoming changes detected. Diff statistics:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
git diff --stat HEAD.."$REMOTE_REF"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Dependency change alert ──────────────────────────────────────────────────
DEP_CHANGES=$(git diff HEAD.."$REMOTE_REF" -- \
  package.json pyproject.toml requirements.txt requirements*.txt 2>/dev/null || true)

if [ -n "$DEP_CHANGES" ]; then
    echo ""
    echo "🚨 DEPENDENCY FILES CHANGED — Review carefully before proceeding:"
    echo "$DEP_CHANGES" | grep "^[+-]" | grep -v "^---\|^+++" | head -40
    echo ""
    echo "   Action required: verify no new packages with unknown provenance."
fi

# ── Archive diff for forensic trail ─────────────────────────────────────────
echo "📦 Archiving diff to $PATCH_FILE (never deleted — forensic record)..."
git diff HEAD.."$REMOTE_REF" > "$PATCH_FILE"
echo "   Commit range: $(git rev-parse --short HEAD)..$(git rev-parse --short "$REMOTE_REF")"

echo ""
echo "Review $PATCH_FILE before confirming."
read -r -p "❓ Proceed with merge? (y/N): " choice
case "$choice" in
  y|Y )
    echo "✅ Merging $REMOTE/$BRANCH..."
    git merge "$REMOTE_REF"
    echo "🎉 Sync complete. Running security audit..."
    bash "$(dirname "$0")/run_audit.sh"
    ;;
  * )
    echo "❌ Merge aborted. Diff archived at $PATCH_FILE for reference."
    exit 1
    ;;
esac
