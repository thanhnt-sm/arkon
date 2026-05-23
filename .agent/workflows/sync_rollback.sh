#!/usr/bin/env bash
# sync_rollback.sh
# One-command rollback after a problematic upstream merge.
#
# Modes:
#   sync_rollback.sh                       # rollback last merge (most common)
#   sync_rollback.sh last                  # alias for the above
#   sync_rollback.sh <patch-file>          # reverse-apply a forensic patch
#   sync_rollback.sh <commit-sha>          # hard reset (destructive — prompts confirm)
#   sync_rollback.sh --list                # list candidate merges + patches
#
# Always non-destructive by default. The hard-reset mode requires explicit yes.

set -uo pipefail

TARGET="${1:-last}"

list_candidates() {
  echo "Recent merge commits (newest first):"
  git log --merges -10 --format='  %h  %ci  %s' 2>/dev/null || echo "  (none)"
  echo ""
  echo "Archived forensic patches:"
  ls -1t .agent/sync_history/*.patch 2>/dev/null | head -10 | sed 's/^/  /' || echo "  (none)"
}

run_audit_hint() {
  echo ""
  echo "✅ Rollback complete. Verify state:"
  echo "   bash .agent/workflows/run_audit.sh"
}

case "$TARGET" in
  --list)
    list_candidates
    exit 0
    ;;
  --help|-h)
    sed -n '2,/^# Always/p' "$0" | sed 's/^# //;s/^#$//'
    exit 0
    ;;
  last|"")
    # Most common path: revert the latest merge commit.
    LAST_MERGE=$(git log --merges -1 --format=%H 2>/dev/null || echo "")
    if [ -z "$LAST_MERGE" ]; then
      echo "❌ No merge commit found in history." >&2
      exit 1
    fi
    SHORT=${LAST_MERGE:0:12}
    SUBJECT=$(git log -1 --format=%s "$LAST_MERGE" 2>/dev/null)
    echo "🔄 Reverting last merge: $SHORT — $SUBJECT"
    # `-m 1` keeps the first parent (typically our branch's history) and
    # backs out everything brought in by the second parent (upstream).
    if git revert -m 1 "$LAST_MERGE" --no-edit; then
      run_audit_hint
      exit 0
    else
      echo "❌ git revert failed — manual resolution required." >&2
      echo "   Conflict-marked files: $(git diff --name-only --diff-filter=U | tr '\n' ' ')" >&2
      exit 1
    fi
    ;;
  *.patch)
    if [ ! -f "$TARGET" ]; then
      echo "❌ Patch file not found: $TARGET" >&2
      exit 1
    fi
    echo "🔄 Reverse-applying patch: $TARGET"
    if ! git apply --reverse --check "$TARGET" 2>/dev/null; then
      echo "❌ Patch cannot be cleanly reversed against current tree." >&2
      echo "   Likely cause: tree drifted after the patch was archived." >&2
      echo "   Manual options: cherry-pick the specific reverse, or use a commit-sha rollback." >&2
      exit 1
    fi
    git apply --reverse "$TARGET"
    git add -A
    git commit -m "revert: rollback patch $(basename "$TARGET")"
    run_audit_hint
    exit 0
    ;;
  *)
    # Treat as a commit ref → hard reset (destructive, requires confirmation).
    if ! git rev-parse "$TARGET" >/dev/null 2>&1; then
      echo "❌ Not a valid git ref: $TARGET" >&2
      echo "   Try: bash $0 --list" >&2
      exit 1
    fi
    SHORT_TARGET=$(git rev-parse --short "$TARGET")
    SHORT_HEAD=$(git rev-parse --short HEAD)
    echo "⚠️  Hard reset HEAD ($SHORT_HEAD) → $SHORT_TARGET"
    echo "   This is DESTRUCTIVE — any commits between $SHORT_TARGET and HEAD will be unreachable."
    printf "   Confirm (type 'yes' to proceed): "
    read -r confirm
    if [ "$confirm" = "yes" ]; then
      git reset --hard "$TARGET"
      run_audit_hint
      exit 0
    else
      echo "Aborted."
      exit 1
    fi
    ;;
esac
