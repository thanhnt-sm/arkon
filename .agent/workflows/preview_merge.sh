#!/usr/bin/env bash
# preview_merge.sh
# Materialize an upstream merge on a disposable branch so the user can review
# `git diff main...preview` BEFORE touching the live branch.
#
# Per-category strategy:
#   safe-upstream    → checkout upstream version of the file
#   keep-local       → no-op (preserves local)
#   needs-merge      → git merge-file (in-place 3-way merge, conflict markers OK)
#   security-risk    → skip + log (file blocked from preview)
#   upstream-deleted → record but require explicit user decision (skip in preview)
#   local-deleted    → no-op (already gone locally)
#
# Usage:
#   preview_merge.sh <conflicts.json> [upstream-ref]
#
# Outputs:
#   - New branch `merge-preview-<timestamp>` containing the materialized merge.
#   - Log at .agent/sync_history/preview-<branch>.log

set -euo pipefail

CONFLICTS_JSON="${1:-}"
UPSTREAM="${2:-upstream/main}"

if [ -z "$CONFLICTS_JSON" ]; then
  echo "Usage: $0 <conflicts.json> [upstream-ref]" >&2
  exit 1
fi
[ -f "$CONFLICTS_JSON" ] || { echo "❌ Not found: $CONFLICTS_JSON" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "❌ jq required" >&2; exit 4; }

git rev-parse --git-dir >/dev/null 2>&1 || { echo "❌ Not a git repo" >&2; exit 3; }
git rev-parse "$UPSTREAM" >/dev/null 2>&1 || { echo "❌ Ref not found: $UPSTREAM" >&2; exit 2; }

# Refuse to run with uncommitted changes — too easy to lose work otherwise.
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "❌ Working tree has uncommitted changes. Commit or stash first." >&2
  exit 1
fi

CURRENT_BRANCH=$(git symbolic-ref --short HEAD 2>/dev/null) || {
  echo "❌ Detached HEAD — checkout a branch first." >&2; exit 3; }

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
TMP_BRANCH="merge-preview-${TIMESTAMP}"
# Keep the log OUTSIDE the working tree — writing inside .agent/sync_history/
# leaves modifications that block `git switch` back to the original branch.
HISTORY_DIR="${TMPDIR:-/tmp}/arkon-sync-history"
LOG="${HISTORY_DIR}/preview-${TMP_BRANCH}.log"
mkdir -p "$HISTORY_DIR"

log_both() {
  echo "$@"
  echo "$@" >> "$LOG"
}

log_both "🌿 Creating preview branch: $TMP_BRANCH"
log_both "   from: $CURRENT_BRANCH"
log_both "   upstream: $UPSTREAM"
log_both "   conflicts: $CONFLICTS_JSON"
log_both ""

git switch -c "$TMP_BRANCH" >> "$LOG" 2>&1

# Rollback helper: jump back to original branch if anything fails mid-flight.
restore_on_error() {
  local rc=$?
  echo "" >> "$LOG"
  echo "❌ preview_merge failed (exit $rc) — restoring $CURRENT_BRANCH" >> "$LOG"
  git switch "$CURRENT_BRANCH" >> "$LOG" 2>&1 || true
  git branch -D "$TMP_BRANCH" >> "$LOG" 2>&1 || true
  echo "" >&2
  echo "❌ preview failed — see $LOG" >&2
  exit "$rc"
}
trap restore_on_error ERR

# Count files per category for summary.
COUNTS_SAFE=0
COUNTS_KEEP=0
COUNTS_MERGE=0
COUNTS_SECURITY=0
COUNTS_UP_DEL=0
COUNTS_LOCAL_DEL=0

# Iterate categorized files. jq emits one TSV row per file.
while IFS=$'\t' read -r cat file; do
  [ -z "$file" ] && continue
  case "$cat" in
    safe-upstream)
      log_both "  [safe-upstream] $file ← checkout upstream"
      git checkout "$UPSTREAM" -- "$file" >> "$LOG" 2>&1 || \
        log_both "    ⚠️  checkout failed for $file"
      COUNTS_SAFE=$((COUNTS_SAFE+1))
      ;;
    keep-local)
      log_both "  [keep-local]    $file ← no-op (local kept)"
      COUNTS_KEEP=$((COUNTS_KEEP+1))
      ;;
    needs-merge)
      log_both "  [needs-merge]   $file ← 3-way merge (may produce conflict markers)"
      # Materialize upstream version to a temp file.
      tmp_upstream=$(mktemp -t arkon-merge.XXXXXX)
      git show "${UPSTREAM}:${file}" > "$tmp_upstream" 2>>"$LOG" || {
        log_both "    ⚠️  upstream version unavailable; treating as keep-local"
        rm -f "$tmp_upstream"
        continue
      }
      base_blob=$(git merge-base HEAD "$UPSTREAM" 2>/dev/null)
      tmp_base=$(mktemp -t arkon-merge-base.XXXXXX)
      git show "${base_blob}:${file}" > "$tmp_base" 2>>"$LOG" || : > "$tmp_base"
      # git merge-file writes conflict markers in-place.
      if git merge-file --diff3 -p "$file" "$tmp_base" "$tmp_upstream" > "${file}.merged" 2>>"$LOG"; then
        mv "${file}.merged" "$file"
        log_both "    ✅ merged cleanly"
      else
        mv "${file}.merged" "$file"
        log_both "    ⚠️  conflict markers inserted — manual edit required"
      fi
      rm -f "$tmp_upstream" "$tmp_base"
      COUNTS_MERGE=$((COUNTS_MERGE+1))
      ;;
    security-risk)
      log_both "  [security-risk] $file ← BLOCKED (audit flagged)"
      COUNTS_SECURITY=$((COUNTS_SECURITY+1))
      ;;
    upstream-deleted)
      log_both "  [upstream-deleted] $file ← deferred (manual decision required)"
      COUNTS_UP_DEL=$((COUNTS_UP_DEL+1))
      ;;
    local-deleted)
      log_both "  [local-deleted] $file ← no-op (already removed locally)"
      COUNTS_LOCAL_DEL=$((COUNTS_LOCAL_DEL+1))
      ;;
    *)
      log_both "  [unknown:$cat] $file ← skipped"
      ;;
  esac
done < <(jq -r '.[] | [.category, .file] | @tsv' "$CONFLICTS_JSON")

# Stage and commit the materialized merge so reviewers can `git diff` cleanly.
git add -A >> "$LOG" 2>&1 || true
if git diff --cached --quiet; then
  git commit --allow-empty -m "preview: merge ${UPSTREAM} (auto-categorized) — no file changes" \
    >> "$LOG" 2>&1 || true
else
  git commit -m "preview: merge ${UPSTREAM} (auto-categorized)

safe-upstream: $COUNTS_SAFE
keep-local: $COUNTS_KEEP
needs-merge: $COUNTS_MERGE
security-risk: $COUNTS_SECURITY
upstream-deleted: $COUNTS_UP_DEL
local-deleted: $COUNTS_LOCAL_DEL" >> "$LOG" 2>&1 || true
fi

trap - ERR

# Return to original branch — preview lives as a sibling, ready for review.
# IMPORTANT: do NOT redirect to $LOG here. The log file was just committed
# into the preview branch; appending to it leaves an unstaged modification
# that blocks `git switch`.
git switch "$CURRENT_BRANCH" >/dev/null 2>&1

echo ""
echo "✅ Preview branch ready: $TMP_BRANCH"
echo ""
echo "   safe-upstream:     $COUNTS_SAFE"
echo "   keep-local:        $COUNTS_KEEP"
echo "   needs-merge:       $COUNTS_MERGE   (may contain conflict markers)"
echo "   security-risk:     $COUNTS_SECURITY (BLOCKED from preview)"
echo "   upstream-deleted:  $COUNTS_UP_DEL  (manual decision)"
echo "   local-deleted:     $COUNTS_LOCAL_DEL"
echo ""
echo "   Review diff:  git diff $CURRENT_BRANCH...$TMP_BRANCH"
echo "   Approve:      git switch $CURRENT_BRANCH && git merge --no-ff $TMP_BRANCH"
echo "   Reject:       git branch -D $TMP_BRANCH"
echo ""
echo "   Log: $LOG"
