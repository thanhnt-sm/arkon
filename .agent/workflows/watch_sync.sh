#!/usr/bin/env bash
# ==============================================================================
# Arkon Sync Watcher
# Monitors .git/FETCH_HEAD (or a configurable path) and runs the security
# audit whenever an upstream fetch lands. Designed to catch ambient `git fetch`
# (IDE, cron, other tooling) that would otherwise bypass safe_sync.sh.
#
# Usage:
#   bash .agent/workflows/watch_sync.sh                    # foreground loop
#   bash .agent/workflows/watch_sync.sh --once             # single audit, no watch
#   WATCH_FILE=.git/FETCH_HEAD bash watch_sync.sh          # override target
#   WATCH_DEBOUNCE_SECONDS=10 bash watch_sync.sh           # tune debounce
#
# Cross-platform:
#   macOS  → uses fswatch (brew install fswatch)
#   Linux  → uses inotifywait (apt install inotify-tools)
#
# Concurrency:
#   PID file at .agent/sync_history/watch.pid prevents double-start.
#   If an audit is in progress when an event fires, the event is coalesced.
#
# Log:
#   Structured one-line-per-audit log at .agent/sync_history/watch.log
#   Format: <iso8601> exit=<code> patch=<patchfile-or-none>
# ==============================================================================

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
AUDIT_SCRIPT="$SCRIPT_DIR/run_audit.sh"
HISTORY_DIR="$( cd "$SCRIPT_DIR/../.." && pwd )/.agent/sync_history"
PID_FILE="$HISTORY_DIR/watch.pid"
LOG_FILE="$HISTORY_DIR/watch.log"
WATCH_FILE="${WATCH_FILE:-.git/FETCH_HEAD}"
WATCH_DEBOUNCE_SECONDS="${WATCH_DEBOUNCE_SECONDS:-5}"
MODE="loop"

# ─── Args ─────────────────────────────────────────────────────────────────
while [ "$#" -gt 0 ]; do
    case "$1" in
        --once)   MODE="once"; shift ;;
        --help|-h)
            sed -n '2,/^# ===/p' "$0" | sed 's/^# //;s/^#$//'
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 64
            ;;
    esac
done

mkdir -p "$HISTORY_DIR"

# ─── Logging ──────────────────────────────────────────────────────────────
log()  { echo "[$(date +%H:%M:%S)] $*"; }
audit_log_line() {
    local exit_code="$1" patch_file="${2:-none}"
    printf '%s exit=%s patch=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$exit_code" "$patch_file" \
        >> "$LOG_FILE"
}

# ─── Pre-flight: required tools (loop mode only) ─────────────────────────
detect_watcher() {
    if command -v fswatch >/dev/null 2>&1; then
        echo "fswatch"
    elif command -v inotifywait >/dev/null 2>&1; then
        echo "inotifywait"
    else
        echo ""
    fi
}

WATCHER=""
if [ "$MODE" = "loop" ]; then
    WATCHER=$(detect_watcher)
    if [ -z "$WATCHER" ]; then
        cat >&2 <<'EOF'
❌ No filesystem watcher available.
   Install one:
     macOS: brew install fswatch
     Linux: apt install inotify-tools   (or: dnf install inotify-tools)
   Or run a single audit without watching:
     bash .agent/workflows/watch_sync.sh --once
EOF
        exit 127
    fi
fi

# ─── Concurrency: PID lock ────────────────────────────────────────────────
acquire_lock() {
    if [ -f "$PID_FILE" ]; then
        local existing_pid
        existing_pid=$(cat "$PID_FILE" 2>/dev/null || echo "")
        if [ -n "$existing_pid" ] && kill -0 "$existing_pid" 2>/dev/null; then
            log "❌ watcher already running (pid $existing_pid). Stop it first."
            exit 1
        fi
        log "ℹ️  stale pid file removed (pid $existing_pid not running)"
    fi
    echo "$$" > "$PID_FILE"
}
release_lock() {
    [ -f "$PID_FILE" ] && rm -f "$PID_FILE"
}

# ─── Audit invocation (handles concurrency + debounce coalescing) ─────────
audit_running=0
audit_pending=0

run_audit() {
    if [ "$audit_running" -eq 1 ]; then
        audit_pending=1
        log "⏸  audit in progress — coalescing pending event"
        return
    fi
    audit_running=1
    log "🔍 running security audit"
    local patch_file=""
    if [ -n "${AUDIT_PATCH_FILE:-}" ] && [ -f "$AUDIT_PATCH_FILE" ]; then
        patch_file="$AUDIT_PATCH_FILE"
    fi
    local exit_code=0
    bash "$AUDIT_SCRIPT" || exit_code=$?
    audit_log_line "$exit_code" "${patch_file:-none}"
    case "$exit_code" in
        0) log "✅ audit PASS (exit 0)" ;;
        2) log "⚠️  audit WARN (exit 2) — review $LOG_FILE" ;;
        1) log "❌ audit FAIL (exit 1) — review $LOG_FILE" ;;
        *) log "❓ audit unknown exit=$exit_code" ;;
    esac
    audit_running=0
    if [ "$audit_pending" -eq 1 ]; then
        audit_pending=0
        log "▶ replaying coalesced event"
        run_audit
    fi
}

# ─── Debounce: collapse rapid events into a single audit ──────────────────
debounce_then_run() {
    local last_event_at now
    last_event_at=$(date +%s)
    while :; do
        now=$(date +%s)
        if [ $((now - last_event_at)) -ge "$WATCH_DEBOUNCE_SECONDS" ]; then
            run_audit
            return
        fi
        # Sleep a tick and re-check; if new event arrived, last_event_at gets
        # refreshed by the caller via the EVENT_TS file.
        sleep 1
        if [ -f "$HISTORY_DIR/.watch_event" ]; then
            last_event_at=$(cat "$HISTORY_DIR/.watch_event" 2>/dev/null || echo "$now")
            rm -f "$HISTORY_DIR/.watch_event"
        fi
    done
}

# ─── Cleanup on shutdown ──────────────────────────────────────────────────
shutdown() {
    log "🛑 shutting down watcher"
    release_lock
    # Kill any child watcher process.
    if [ -n "${WATCHER_PID:-}" ] && kill -0 "$WATCHER_PID" 2>/dev/null; then
        kill "$WATCHER_PID" 2>/dev/null || true
    fi
    exit 0
}
trap shutdown INT TERM

# ─── --once mode: single audit, no watcher ────────────────────────────────
if [ "$MODE" = "once" ]; then
    acquire_lock
    run_audit
    release_lock
    exit 0
fi

# ─── Loop mode ────────────────────────────────────────────────────────────
acquire_lock

if [ ! -f "$WATCH_FILE" ]; then
    log "creating empty $WATCH_FILE to watch..."
    mkdir -p "$(dirname "$WATCH_FILE")"
    touch "$WATCH_FILE"
fi

log "👁  monitoring $WATCH_FILE via $WATCHER (debounce ${WATCH_DEBOUNCE_SECONDS}s)"
log "   pid=$$ log=$LOG_FILE"
log "   Ctrl+C to stop."

# Tail watcher events line-by-line; each line triggers debounce + audit.
case "$WATCHER" in
    fswatch)
        # -o: count-only event lines. Each line = "one or more events".
        fswatch -o "$WATCH_FILE" 2>/dev/null | while read -r _; do
            log "🔄 event on $WATCH_FILE"
            date +%s > "$HISTORY_DIR/.watch_event"
            debounce_then_run
        done
        ;;
    inotifywait)
        # -m: monitor (no exit). -q: quiet. -e modify,close_write,move_self.
        inotifywait -m -q -e modify,close_write,move_self "$WATCH_FILE" 2>/dev/null | while read -r _; do
            log "🔄 event on $WATCH_FILE"
            date +%s > "$HISTORY_DIR/.watch_event"
            debounce_then_run
        done
        ;;
esac

shutdown
