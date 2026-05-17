#!/bin/bash

# Watcher for Arkon Git Sync
# Detects changes to .git/FETCH_HEAD and triggers security audit.

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
AUDIT_SCRIPT="$SCRIPT_DIR/run_audit.sh"
WATCH_FILE=".git/FETCH_HEAD"

if [ ! -f "$WATCH_FILE" ]; then
    echo "Creating empty $WATCH_FILE to watch..."
    touch "$WATCH_FILE"
fi

echo "👁️ Monitoring $WATCH_FILE for changes (upstream sync)..."
echo "   Press Ctrl+C to stop."

# Use fswatch to monitor the file
# -1: Exit after first event (we use a loop to restart)
# -o: Only print the event count
fswatch -o "$WATCH_FILE" | while read -r event; do
    echo -e "\n🔄 Change detected in $WATCH_FILE. Triggering Security Audit..."
    bash "$AUDIT_SCRIPT"
    echo -e "\n👁️ Resuming monitor..."
done
