#!/usr/bin/env bash
# loc-counter.sh
# Language-aware semantic LOC counter for unified diffs.
# Sourced by categorize_conflicts.sh; not executable on its own.
# Bash 3.2 compatible — no associative arrays.

if [ -n "${ARKON_LOC_COUNTER_LOADED:-}" ]; then
  return 0 2>/dev/null || exit 0
fi
ARKON_LOC_COUNTER_LOADED=1

# ---------------------------------------------------------------------------
# comment_pattern_for <ext>
# Echo the grep -E pattern that matches a line-leading single-line comment
# for the given file extension. Empty for unknown/markdown (no skipping).
# Patterns anchor on `^[+-][[:space:]]*` so they apply to diff +/- lines.
# ---------------------------------------------------------------------------
comment_pattern_for() {
  case "$1" in
    py|sh|bash|zsh|yaml|yml|toml|r|R|rb|conf|cfg|ini|env)
      echo '^[+-][[:space:]]*#'
      ;;
    js|jsx|ts|tsx|mjs|cjs|c|cpp|cc|cxx|h|hpp|go|rs|java|kt|swift|scala|cs|php|m|mm)
      echo '^[+-][[:space:]]*(//|/\*|\*[^/]|\*$)'
      ;;
    css|scss|sass|less)
      echo '^[+-][[:space:]]*(/\*|\*[^/]|\*$)'
      ;;
    html|xml|svg|vue|svelte)
      echo '^[+-][[:space:]]*<!--'
      ;;
    sql|lua)
      echo '^[+-][[:space:]]*--'
      ;;
    lisp|clj|cljs|el)
      echo '^[+-][[:space:]]*;'
      ;;
    md|mdx|markdown|txt|rst)
      # No comment skipping — every change counts.
      echo ''
      ;;
    *)
      # Conservative default — covers common families.
      echo '^[+-][[:space:]]*(#|//|/\*)'
      ;;
  esac
}

# ---------------------------------------------------------------------------
# count_semantic_loc <range> <file>
# Count non-trivial changed lines in `git diff <range> -- <file>`.
# Excludes: file headers (+++/---), blank lines, single-line comments.
# Returns 0 for binary files / empty diffs.
# ---------------------------------------------------------------------------
count_semantic_loc() {
  local range="$1"
  local file="$2"
  local raw
  raw=$(git diff "$range" -- "$file" 2>/dev/null)
  [ -z "$raw" ] && { echo 0; return 0; }

  # Binary file marker emitted by `git diff` ("Binary files ... differ").
  if echo "$raw" | head -3 | grep -q "Binary files"; then
    echo 0
    return 0
  fi

  local ext="${file##*.}"
  [ "$ext" = "$file" ] && ext=""
  local comment_re
  comment_re=$(comment_pattern_for "$ext")

  local filtered
  filtered=$(echo "$raw" \
    | grep -E '^[+-]' \
    | grep -vE '^[+-]{3}' \
    | grep -vE '^[+-][[:space:]]*$')

  if [ -n "$comment_re" ]; then
    filtered=$(echo "$filtered" | grep -vE "$comment_re" || true)
  fi

  if [ -z "$filtered" ]; then
    echo 0
  else
    echo "$filtered" | wc -l | tr -d ' \n'
  fi
}
