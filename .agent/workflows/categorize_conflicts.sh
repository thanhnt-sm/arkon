#!/usr/bin/env bash
# categorize_conflicts.sh
# Deterministic per-file conflict categorization between HEAD and an upstream ref.
# Same input → same output. Used by preview_merge.sh and reporting.
# Bash 3.2 compatible — no associative arrays.
#
# Usage:
#   categorize_conflicts.sh [upstream-ref] [security-overlay-file] [--json|--csv|--summary] [--filter-category=X]
#
# Defaults:
#   upstream-ref          = upstream/main
#   security-overlay      = (none)
#   output format         = json
#
# Env:
#   MIN_SEMANTIC_LOC   threshold for keep-local/needs-merge (default 5)
#
# Exit codes (per spec):
#   0 = success | 1 = bad args | 2 = upstream ref missing | 3 = repo state bad | 4 = missing dep

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# shellcheck source=lib/loc-counter.sh
source "$SCRIPT_DIR/lib/loc-counter.sh"

MIN_SEMANTIC_LOC="${MIN_SEMANTIC_LOC:-5}"
OUTPUT_FORMAT="json"
FILTER_CATEGORY=""

# ─── Arg parsing ──────────────────────────────────────────────────────────
UPSTREAM=""
SECURITY_OVERLAY=""
POSITIONAL_TAKEN=0

for arg in "$@"; do
  case "$arg" in
    --json)               OUTPUT_FORMAT="json" ;;
    --csv)                OUTPUT_FORMAT="csv" ;;
    --summary)            OUTPUT_FORMAT="summary" ;;
    --filter-category=*)  FILTER_CATEGORY="${arg#*=}" ;;
    --help|-h)
      sed -n '2,/^# Exit codes/p' "$0" | sed 's/^# //;s/^#$//'
      exit 0
      ;;
    --*)
      echo "[categorize] unknown flag: $arg" >&2
      exit 1
      ;;
    *)
      if [ "$POSITIONAL_TAKEN" -eq 0 ]; then
        UPSTREAM="$arg"; POSITIONAL_TAKEN=1
      elif [ "$POSITIONAL_TAKEN" -eq 1 ]; then
        SECURITY_OVERLAY="$arg"; POSITIONAL_TAKEN=2
      else
        echo "[categorize] too many positional args" >&2
        exit 1
      fi
      ;;
  esac
done

UPSTREAM="${UPSTREAM:-upstream/main}"

# ─── Pre-flight ───────────────────────────────────────────────────────────
command -v jq  >/dev/null 2>&1 || { echo "[categorize] jq required (brew install jq)" >&2; exit 4; }
command -v git >/dev/null 2>&1 || { echo "[categorize] git required" >&2; exit 4; }
git rev-parse --git-dir >/dev/null 2>&1 || { echo "[categorize] not inside a git repo" >&2; exit 3; }
git rev-parse "$UPSTREAM" >/dev/null 2>&1 || {
  echo "[categorize] ref not found: $UPSTREAM (run: git fetch upstream)" >&2; exit 2; }
git symbolic-ref --short HEAD >/dev/null 2>&1 || {
  echo "[categorize] detached HEAD — checkout a branch first" >&2; exit 3; }

# ─── Security overlay — held as newline-separated string (bash 3 safe) ───
SECURITY_LIST=""
if [ -n "$SECURITY_OVERLAY" ]; then
  if [ ! -f "$SECURITY_OVERLAY" ]; then
    echo "[categorize] security overlay file not found: $SECURITY_OVERLAY" >&2
    exit 1
  fi
  SECURITY_LIST=$(grep -v '^[[:space:]]*$' "$SECURITY_OVERLAY" || true)
fi

is_security_file() {
  [ -z "$SECURITY_LIST" ] && return 1
  printf '%s\n' "$SECURITY_LIST" | grep -Fxq "$1"
}

# ─── Cache merge-base + diff name list ────────────────────────────────────
MERGE_BASE=$(git merge-base HEAD "$UPSTREAM" 2>/dev/null || echo "")
if [ -z "$MERGE_BASE" ]; then
  echo "[categorize] no common ancestor between HEAD and $UPSTREAM" >&2
  exit 3
fi

# Files changed between merge-base and upstream — those are the ones with
# upstream movement that we need to decide on.
CHANGED_FILES=$(git diff "$MERGE_BASE..$UPSTREAM" --name-only 2>/dev/null || true)
TOTAL=$(echo "$CHANGED_FILES" | grep -c . || true)

# ─── Iterate ──────────────────────────────────────────────────────────────
RESULTS=()
COUNT=0

# Sort for determinism — same diff name set always processed in same order.
SORTED_FILES=$(echo "$CHANGED_FILES" | grep . | LC_ALL=C sort -u || true)

while IFS= read -r f; do
  [ -z "$f" ] && continue
  COUNT=$((COUNT+1))
  if [ "$TOTAL" -gt 100 ] && [ $((COUNT % 50)) -eq 0 ]; then
    echo "[categorize] processed $COUNT/$TOTAL files..." >&2
  fi

  CAT=""
  LOCAL_LOC=0
  UPSTREAM_LOC=0
  LOCAL_COMMITS=0
  UPSTREAM_COMMITS=0

  # 1. Security overlay overrides everything.
  if is_security_file "$f"; then
    CAT="security-risk"
  else
    # 2. Deletion states.
    UPSTREAM_EXISTS=1
    git cat-file -e "${UPSTREAM}:${f}" 2>/dev/null || UPSTREAM_EXISTS=0
    LOCAL_EXISTS=1
    git cat-file -e "HEAD:${f}" 2>/dev/null || LOCAL_EXISTS=0

    if [ "$UPSTREAM_EXISTS" -eq 0 ] && [ "$LOCAL_EXISTS" -eq 1 ]; then
      CAT="upstream-deleted"
    elif [ "$UPSTREAM_EXISTS" -eq 1 ] && [ "$LOCAL_EXISTS" -eq 0 ]; then
      CAT="local-deleted"
    elif [ "$UPSTREAM_EXISTS" -eq 0 ] && [ "$LOCAL_EXISTS" -eq 0 ]; then
      # Deleted on both sides — skip.
      continue
    else
      # 3. Standard tree: count local commits + LOC.
      LOCAL_COMMITS=$(git log "$MERGE_BASE..HEAD" --oneline -- "$f" 2>/dev/null | grep -c . || true)
      if [ "$LOCAL_COMMITS" -eq 0 ]; then
        CAT="safe-upstream"
        UPSTREAM_LOC=$(count_semantic_loc "$MERGE_BASE..$UPSTREAM" "$f" 2>/dev/null || echo 0)
      else
        LOCAL_LOC=$(count_semantic_loc "$MERGE_BASE..HEAD" "$f" 2>/dev/null || echo 0)
        UPSTREAM_LOC=$(count_semantic_loc "$MERGE_BASE..$UPSTREAM" "$f" 2>/dev/null || echo 0)
        if [ "$LOCAL_LOC" -gt "$MIN_SEMANTIC_LOC" ] && [ "$UPSTREAM_LOC" -gt "$MIN_SEMANTIC_LOC" ]; then
          CAT="needs-merge"
        elif [ "$LOCAL_LOC" -gt "$MIN_SEMANTIC_LOC" ]; then
          CAT="keep-local"
        else
          CAT="safe-upstream"
        fi
      fi
    fi
  fi

  # Filter (if requested).
  if [ -n "$FILTER_CATEGORY" ] && [ "$CAT" != "$FILTER_CATEGORY" ]; then
    continue
  fi

  # Build metadata.
  UPSTREAM_COMMITS=$(git log "$MERGE_BASE..$UPSTREAM" --oneline -- "$f" 2>/dev/null | grep -c . || true)
  EXT="${f##*.}"
  [ "$EXT" = "$f" ] && EXT=""

  SIZE=0
  if [ -f "$f" ]; then
    SIZE=$(stat -f%z "$f" 2>/dev/null || stat -c%s "$f" 2>/dev/null || echo 0)
  fi

  LAST_LOCAL=$(git log -1 --format=%cI "HEAD" -- "$f" 2>/dev/null || true)
  [ -z "$LAST_LOCAL" ] && LAST_LOCAL_JSON='null' || LAST_LOCAL_JSON="\"$LAST_LOCAL\""
  LAST_UPSTREAM=$(git log -1 --format=%cI "$UPSTREAM" -- "$f" 2>/dev/null || true)
  [ -z "$LAST_UPSTREAM" ] && LAST_UPSTREAM_JSON='null' || LAST_UPSTREAM_JSON="\"$LAST_UPSTREAM\""

  # Build JSON via jq for safe string escaping.
  ENTRY=$(jq -n \
    --arg file "$f" \
    --arg cat "$CAT" \
    --argjson ll "${LOCAL_LOC:-0}" \
    --argjson ul "${UPSTREAM_LOC:-0}" \
    --argjson lc "${LOCAL_COMMITS:-0}" \
    --argjson uc "${UPSTREAM_COMMITS:-0}" \
    --arg ll_iso "${LAST_LOCAL:-}" \
    --arg lu_iso "${LAST_UPSTREAM:-}" \
    --arg ext "$EXT" \
    --argjson sz "${SIZE:-0}" \
    '{
       file: $file,
       category: $cat,
       local_loc: $ll,
       upstream_loc: $ul,
       local_commits: $lc,
       upstream_commits: $uc,
       last_local_change: (if $ll_iso == "" then null else $ll_iso end),
       last_upstream_change: (if $lu_iso == "" then null else $lu_iso end),
       ext: $ext,
       size_bytes: $sz
     }' \
    | jq -cS .)

  RESULTS+=("$ENTRY")
done <<< "$SORTED_FILES"

# ─── Output ───────────────────────────────────────────────────────────────
# Stitch the per-file JSON entries into a single array literal (no trailing
# newline — caller decides). Empty array stays empty.
print_results_json() {
  if [ "${#RESULTS[@]}" -eq 0 ]; then
    printf '[]'
    return
  fi
  printf '['
  local i=0
  while [ "$i" -lt "${#RESULTS[@]}" ]; do
    [ "$i" -gt 0 ] && printf ','
    printf '%s' "${RESULTS[$i]}"
    i=$((i+1))
  done
  printf ']'
}

case "$OUTPUT_FORMAT" in
  json)
    print_results_json
    printf '\n'
    ;;
  csv)
    echo "file,category,local_loc,upstream_loc,local_commits,upstream_commits,last_local_change,last_upstream_change,ext,size_bytes"
    for entry in "${RESULTS[@]+"${RESULTS[@]}"}"; do
      echo "$entry" | jq -r '[.file, .category, .local_loc, .upstream_loc, .local_commits, .upstream_commits, .last_local_change, .last_upstream_change, .ext, .size_bytes] | @csv'
    done
    ;;
  summary)
    if [ "${#RESULTS[@]}" -eq 0 ]; then
      echo "total: 0"
    else
      print_results_json | jq -r '
        group_by(.category)
        | map({key: .[0].category, value: length})
        | from_entries
        | to_entries
        | map("\(.key): \(.value)")
        | join("\n")
      '
      printf 'total: %d\n' "${#RESULTS[@]}"
    fi
    ;;
esac
