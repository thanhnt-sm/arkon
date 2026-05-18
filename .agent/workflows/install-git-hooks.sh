#!/usr/bin/env bash
# Installs security-enforcing git hooks into .git/hooks/.
# Run once after cloning: bash .agent/workflows/install-git-hooks.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_SRC="$REPO_ROOT/.agent/git-hooks"
HOOKS_DST="$REPO_ROOT/.git/hooks"

HOOKS=("post-merge")

echo "📎 Installing git hooks from $HOOKS_SRC → $HOOKS_DST"

for hook in "${HOOKS[@]}"; do
  SRC="$HOOKS_SRC/$hook"
  DST="$HOOKS_DST/$hook"

  if [ ! -f "$SRC" ]; then
    echo "⚠️  Source hook not found: $SRC — skipping"
    continue
  fi

  if [ -f "$DST" ] && [ ! -L "$DST" ]; then
    echo "⚠️  Existing hook at $DST — backing up to ${DST}.bak"
    mv "$DST" "${DST}.bak"
  fi

  cp "$SRC" "$DST"
  chmod +x "$DST"
  echo "✅ Installed: $hook"
done

echo ""
echo "🔒 Git hooks installed. Security audit will auto-run after every merge."
echo "   To uninstall: rm .git/hooks/post-merge"
