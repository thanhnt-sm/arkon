#!/usr/bin/env bash
# ==============================================================================
# Upstream Sync Gateway (Safe Sync Workflow)
# Prevents blind git pull from upstream. Forces diff review + dependency alert.
# Diff is archived (never deleted) for forensics.
#
# Modes:
#   safe_sync.sh [remote] [branch]            # interactive — fetch, review, prompt merge
#   SYNC_MODE=dryrun safe_sync.sh ...         # fetch + archive only, no prompt, no merge
#   safe_sync.sh [remote] [branch] --merge    # hard gate: refuse without PASS audit report
#
# Exit codes:
#   0 = success (up-to-date, dry-run archived, or merge completed)
#   1 = guard failure (missing remote, no audit report, audit not PASS, user abort)
# ==============================================================================

set -euo pipefail

REMOTE=${1:-upstream}
BRANCH=${2:-main}
MODE_FLAG=${3:-}
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
HISTORY_DIR=".agent/sync_history"
PATCH_FILE="$HISTORY_DIR/${TIMESTAMP}_${REMOTE}_${BRANCH}.patch"
# SYNC_MODE=dryrun → fetch + archive only, no interactive prompt, no merge.
# Used by ck:sync-audit-upstream skill for pre-merge analysis.
SYNC_MODE=${SYNC_MODE:-interactive}
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

mkdir -p "$HISTORY_DIR"

if ! git remote | grep -q "^$REMOTE$"; then
    echo "❌ Remote '$REMOTE' not found. Add it: git remote add upstream <url>"
    exit 1
fi

# ─── Force-push detection ───────────────────────────────────────────────────
# Capture the previous upstream tip before fetch so we can spot history rewrites.
PREV_UPSTREAM_REF=""
if git rev-parse --verify "refs/remotes/$REMOTE/$BRANCH" >/dev/null 2>&1; then
    PREV_UPSTREAM_REF=$(git rev-parse "refs/remotes/$REMOTE/$BRANCH")
fi

echo "🔄 Fetching $REMOTE/$BRANCH..."
git fetch "$REMOTE" "$BRANCH"

LOCAL=$(git rev-parse @)
REMOTE_REF=$(git rev-parse "$REMOTE/$BRANCH")

if [ "$LOCAL" = "$REMOTE_REF" ]; then
    echo "✅ Already up to date with $REMOTE/$BRANCH."
    exit 0
fi

# Warn-only force-push detection (per Phase 3 decision = warn + log + continue).
FORCE_PUSH_DETECTED=0
if [ -n "$PREV_UPSTREAM_REF" ] && [ "$PREV_UPSTREAM_REF" != "$REMOTE_REF" ]; then
    if ! git merge-base --is-ancestor "$PREV_UPSTREAM_REF" "$REMOTE_REF" 2>/dev/null; then
        FORCE_PUSH_DETECTED=1
        echo ""
        echo "⚠️  FORCE-PUSH DETECTED on $REMOTE/$BRANCH"
        echo "   Previous tip: ${PREV_UPSTREAM_REF:0:12} no longer reachable from new tip ${REMOTE_REF:0:12}"
        echo "   Upstream rewrote history. Review with extra care."
        mkdir -p "$HISTORY_DIR"
        echo "${TIMESTAMP} force-push ${REMOTE}/${BRANCH} prev=${PREV_UPSTREAM_REF} new=${REMOTE_REF}" \
            >> "$HISTORY_DIR/force-push.log"
    fi
fi

echo ""
echo "⚠️  Incoming changes detected. Diff statistics:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
git diff --stat HEAD.."$REMOTE_REF"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── Dependency change alert ───────────────────────────────────────────────
DEP_CHANGES=$(git diff HEAD.."$REMOTE_REF" -- \
  package.json pyproject.toml requirements.txt requirements*.txt 2>/dev/null || true)

if [ -n "$DEP_CHANGES" ]; then
    echo ""
    echo "🚨 DEPENDENCY FILES CHANGED — Review carefully before proceeding:"
    echo "$DEP_CHANGES" | grep "^[+-]" | grep -v "^---\|^+++" | head -40
    echo ""
    echo "   Action required: verify no new packages with unknown provenance."
fi

# ─── Archive diff for forensic trail ───────────────────────────────────────
echo "📦 Archiving diff to $PATCH_FILE (never deleted — forensic record)..."
git diff HEAD.."$REMOTE_REF" > "$PATCH_FILE"
echo "   Commit range: $(git rev-parse --short HEAD)..$(git rev-parse --short "$REMOTE_REF")"

echo ""
echo "Review $PATCH_FILE before confirming."

# ─── Hard gate: --merge requires PASS audit report matching upstream SHA ───
if [ "$MODE_FLAG" = "--merge" ]; then
    UPSTREAM_SHA="$REMOTE_REF"
    SHORT_SHA=${UPSTREAM_SHA:0:12}

    echo ""
    echo "🔍 Verifying audit report for upstream SHA ${SHORT_SHA}..."

    # Match any report whose frontmatter declares this upstream_sha.
    # nullglob lets the glob expand to nothing instead of literal pattern,
    # so grep doesn't error and trip set -e / pipefail.
    REPORT=""
    shopt -s nullglob
    candidate_reports=(plans/reports/sync-audit-*.md)
    shopt -u nullglob
    if [ "${#candidate_reports[@]}" -gt 0 ]; then
        REPORT=$(grep -l "^upstream_sha:[[:space:]]*${UPSTREAM_SHA}\$" \
                   "${candidate_reports[@]}" 2>/dev/null | head -1 || true)
    fi

    if [ -z "$REPORT" ]; then
        echo "❌ No audit report found with upstream_sha: ${SHORT_SHA}"
        echo "   Required: run a dry-run audit first:"
        echo "     SYNC_MODE=dryrun bash $0 $REMOTE $BRANCH"
        echo "     AUDIT_PATCH_FILE=$PATCH_FILE bash $SCRIPT_DIR/run_audit.sh"
        echo "   Then generate a report with frontmatter:"
        echo "     upstream_sha: ${UPSTREAM_SHA}"
        echo "     audit_status: PASS"
        exit 1
    fi

    if ! grep -Eq "^audit_status:[[:space:]]*PASS[[:space:]]*$" "$REPORT"; then
        STATUS=$(awk -F':' '/^audit_status:/ { gsub(/[[:space:]]/, "", $2); print $2; exit }' "$REPORT")
        echo "❌ Report exists but audit_status=${STATUS:-unknown} (need PASS)"
        echo "   Report: $REPORT"
        echo "   Fix the audit findings or regenerate the report with PASS."
        exit 1
    fi

    if [ "$FORCE_PUSH_DETECTED" -eq 1 ]; then
        echo "⚠️  Proceeding despite force-push warning (logged in $HISTORY_DIR/force-push.log)"
    fi

    echo "✅ Audit PASSED for ${SHORT_SHA} (report: $(basename "$REPORT"))"
    echo "🔀 Merging $REMOTE/$BRANCH..."
    git merge "$REMOTE_REF"
    echo "🎉 Merge complete. Post-merge audit runs via git hook if installed."
    # Best-effort: record merged state in the forensic index.
    if [ -z "${ARKON_AUDIT_NO_INDEX:-}" ] && [ -x "$SCRIPT_DIR/append_index.sh" ]; then
        bash "$SCRIPT_DIR/append_index.sh" \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            "$UPSTREAM_SHA" \
            "$PATCH_FILE" \
            "PASS" \
            "$REPORT" \
            "merged" >/dev/null 2>&1 || true
    fi
    exit 0
fi

# Dry-run mode: exit after archiving — no prompt, no merge.
if [ "$SYNC_MODE" = "dryrun" ]; then
    echo "ℹ️  Dry-run mode: diff archived, no merge executed."
    echo "PATCH_FILE=$PATCH_FILE"
    # Best-effort: record this dry-run in the forensic index.
    if [ -z "${ARKON_AUDIT_NO_INDEX:-}" ] && [ -x "$SCRIPT_DIR/append_index.sh" ]; then
        bash "$SCRIPT_DIR/append_index.sh" \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            "$REMOTE_REF" \
            "$PATCH_FILE" \
            "pending" \
            "" \
            "dry-run" >/dev/null 2>&1 || true
    fi
    exit 0
fi

# ─── Interactive prompt (legacy path) ──────────────────────────────────────
read -r -p "❓ Proceed with merge? (y/N): " choice
case "$choice" in
  y|Y )
    echo "✅ Merging $REMOTE/$BRANCH..."
    git merge "$REMOTE_REF"
    echo "🎉 Sync complete. Running security audit..."
    bash "$SCRIPT_DIR/run_audit.sh"
    ;;
  * )
    echo "❌ Merge aborted. Diff archived at $PATCH_FILE for reference."
    exit 1
    ;;
esac
