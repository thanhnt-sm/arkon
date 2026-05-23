#!/usr/bin/env bash
# update_metrics.sh
# Atomically increment audit counters in .agent/metrics/audit-counters.json.
# Concurrency-safe via flock; best-effort — never fails the calling audit.
#
# Usage:
#   update_metrics.sh <PASS|WARN|FAIL> [audit-log-file]
#
# If an audit log file is provided, per-check counters are derived from
# `▶ <Section>` headers + the [PASS]/[WARN]/[FAIL] line that follows.

set -uo pipefail

STATUS="${1:-}"
AUDIT_LOG="${2:-}"

case "$STATUS" in
  PASS|WARN|FAIL) ;;
  *) echo "[metrics] usage: $0 <PASS|WARN|FAIL> [audit-log]" >&2; exit 1 ;;
esac

# Anchor on the current git working tree so the script targets *the* repo
# that's actually being audited (CI clones it; tests cd into an ephemeral one).
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || REPO_ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/../.." && pwd )"
METRICS_DIR="$REPO_ROOT/.agent/metrics"
METRICS_FILE="$METRICS_DIR/audit-counters.json"
LOCK_FILE="$METRICS_FILE.lock"

mkdir -p "$METRICS_DIR"

# Initialize a fresh counter file if missing.
if [ ! -f "$METRICS_FILE" ]; then
  cat > "$METRICS_FILE" <<'JSON'
{
  "schema_version": 1,
  "last_updated": "",
  "totals": { "audit_runs": 0, "pass": 0, "warn": 0, "fail": 0 },
  "by_check": {},
  "rollbacks_30d": 0,
  "force_push_detections": 0
}
JSON
fi

# Per-check aggregator: emit JSON updates from the audit log.
build_check_updates() {
  [ -z "$AUDIT_LOG" ] && return 0
  [ -f "$AUDIT_LOG" ] || return 0
  awk '
    /^▶ / {
      # Strip leading marker; lowercase + snake_case the section name.
      sec=$0
      sub(/^▶ /, "", sec)
      sec=tolower(sec)
      gsub(/[^a-z0-9]+/, "_", sec)
      gsub(/^_+|_+$/, "", sec)
      current="check_" sec
      next
    }
    /^\[PASS\]/ && current != "" { print current "\tpass";  next }
    /^\[WARN\]/ && current != "" { print current "\twarn";  next }
    /^\[FAIL\]/ && current != "" { print current "\tfail";  next }
  ' "$AUDIT_LOG"
}

# Build a jq filter that increments totals + each per-check counter.
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATUS_LOWER=$(echo "$STATUS" | tr 'A-Z' 'a-z')

JQ_FILTER='.last_updated=$now
  | .totals.audit_runs += 1
  | .totals[$s] += 1'

JQ_ARGS=(--arg now "$NOW" --arg s "$STATUS_LOWER")

# Walk the per-check updates and accumulate them into jq filter.
# We can't safely interpolate variable keys directly into jq filter strings,
# so we build a Bash array of jq expressions and join.
declare -a EXTRA_FILTERS=()
while IFS=$'\t' read -r key result; do
  [ -z "$key" ] && continue
  EXTRA_FILTERS+=("| .by_check[\"$key\"] = ((.by_check[\"$key\"] // {pass:0,warn:0,fail:0}) | .${result} += 1)")
done < <(build_check_updates)

if [ "${#EXTRA_FILTERS[@]}" -gt 0 ]; then
  JQ_FILTER="$JQ_FILTER ${EXTRA_FILTERS[*]}"
fi

# Atomic update inside a flock-guarded critical section.
update_with_lock() {
  local tmp
  tmp=$(mktemp -t arkon-metrics.XXXXXX)
  if ! jq "${JQ_ARGS[@]}" "$JQ_FILTER" "$METRICS_FILE" > "$tmp" 2>/dev/null; then
    rm -f "$tmp"
    echo "[metrics] jq filter failed — leaving counters untouched" >&2
    return 1
  fi
  mv "$tmp" "$METRICS_FILE"
}

# flock isn't always installed on macOS — fall back to no-op locking
# (single-writer assumption is fine for the typical audit cadence).
if command -v flock >/dev/null 2>&1; then
  exec 9>"$LOCK_FILE"
  flock -x 9
  update_with_lock || true
  flock -u 9
else
  update_with_lock || true
fi

echo "[metrics] updated: $STATUS (file: $METRICS_FILE)"
