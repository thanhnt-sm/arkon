#!/usr/bin/env bash
# ==============================================================================
# Upstream Sync Gateway (Safe Sync Workflow)
# Description: Prevents blind `git pull` from an upstream repository.
# Forces a fetch and displays a diff for audit. The user must manually confirm
# before changes are merged.
# ==============================================================================

set -e

# Default to upstream/main if not specified
REMOTE=${1:-upstream}
BRANCH=${2:-main}

# Check if upstream exists
if ! git remote | grep -q "^$REMOTE$"; then
    echo "❌ Error: Remote '$REMOTE' not found. Please add it using:"
    echo "   git remote add upstream <repository-url>"
    exit 1
fi

echo "🔄 Fetching latest changes from $REMOTE/$BRANCH..."
git fetch $REMOTE $BRANCH

# Check if there are incoming changes
LOCAL=$(git rev-parse @)
REMOTE_REF=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_REF" ]; then
    echo "✅ Up to date with $REMOTE/$BRANCH. Nothing to sync."
    exit 0
fi

echo "⚠️  Incoming changes detected. Displaying diff statistics:"
echo "--------------------------------------------------------------------------------"
git diff --stat HEAD..$REMOTE_REF
echo "--------------------------------------------------------------------------------"

echo "🔍 Generating detailed diff for review (saving to .agent/sync_diff.patch)..."
git diff HEAD..$REMOTE_REF > .agent/sync_diff.patch

echo "Please review .agent/sync_diff.patch carefully."
echo "Pay special attention to new dependencies (package.json, pyproject.toml) or new network requests."

read -p "❓ Proceed with merging these changes? (y/N): " choice
case "$choice" in 
  y|Y ) 
    echo "✅ Merging $REMOTE/$BRANCH..."
    git merge $REMOTE_REF
    echo "🧹 Cleaning up diff patch..."
    rm -f .agent/sync_diff.patch
    echo "🎉 Sync complete!"
    ;;
  * ) 
    echo "❌ Merge aborted. Changes remain fetched but not merged."
    exit 1
    ;;
esac
