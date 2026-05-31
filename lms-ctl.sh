#!/usr/bin/env bash
# =============================================================================
# lms-ctl.sh — LM Studio CLI Controller for Arkon
#
# A strict wrapper around `lms` cli to provide highest enforcement, clean 
# processing, complete memory drain handling, and helper tools for Arkon.
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Config & Constants
# ---------------------------------------------------------------------------
RAM_FREE_THRESHOLD_MB=500
UNLOAD_TIMEOUT_S=30

# ---------------------------------------------------------------------------
# Colors & Logging
# ---------------------------------------------------------------------------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

info()    { echo -e "${CYAN}[INFO]${RESET} $*"; }
success() { echo -e "${GREEN}[OK]${RESET}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${RESET} $*"; }
error()   { echo -e "${RED}[ERR]${RESET}  $*" >&2; }
step()    { echo -e "\n${BOLD}▶ $*${RESET}"; }
divider() { echo -e "${CYAN}────────────────────────────────────────────────${RESET}"; }

# ---------------------------------------------------------------------------
# Prerequisite Checks
# ---------------------------------------------------------------------------
check_prereqs() {
  if ! command -v lms &>/dev/null; then
    error "lms (LM Studio CLI) is not installed or not in PATH."
    exit 1
  fi
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
get_llmworker_pid() {
  # find node process with llmworker.js
  pgrep -f "llmworker.js" | head -n 1 || echo ""
}

get_pid_rss_mb() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    echo "0"
    return
  fi
  # macOS ps returns rss in KB. Divide by 1024
  local rss_kb
  rss_kb=$(ps -p "$pid" -o rss= 2>/dev/null | tr -d ' ' || echo "0")
  if [[ -z "$rss_kb" || "$rss_kb" == "0" ]]; then
    echo "0"
  else
    echo "$((rss_kb / 1024))"
  fi
}

# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------
cmd_unload() {
  local model_id=""
  local unload_all=0

  # Parse args
  for arg in "$@"; do
    if [[ "$arg" == "--all" || "$arg" == "-a" ]]; then
      unload_all=1
    elif [[ "$arg" != -* ]]; then
      model_id="$arg"
    fi
  done

  step "Unloading model(s)..."
  if [[ $unload_all -eq 1 ]]; then
    info "Unloading ALL models..."
    lms unload --all || warn "lms unload --all returned non-zero. Attempting RAM drain anyway."
  elif [[ -n "$model_id" ]]; then
    info "Unloading model: $model_id"
    lms unload "$model_id" || warn "Failed to unload $model_id natively. Attempting RAM drain anyway."
  else
    # Interactively unload or unload the only loaded model.
    lms unload
  fi

  # RAM Drain enforcement
  info "Enforcing RAM drain..."
  local worker_pid
  worker_pid=$(get_llmworker_pid)

  if [[ -z "$worker_pid" ]]; then
    success "No llmworker process found. RAM is free."
    return 0
  fi

  local elapsed=0
  local interval=1

  while [[ $elapsed -lt $UNLOAD_TIMEOUT_S ]]; do
    local rss_mb
    rss_mb=$(get_pid_rss_mb "$worker_pid")
    
    if (( rss_mb < RAM_FREE_THRESHOLD_MB )); then
      success "RAM released voluntarily (RSS: ${rss_mb} MB < ${RAM_FREE_THRESHOLD_MB} MB)."
      return 0
    fi
    
    printf "\r${CYAN}[INFO]${RESET} Waiting for RAM release (PID: %s, RSS: %s MB)... %ds" "$worker_pid" "$rss_mb" "$elapsed"
    sleep $interval
    elapsed=$((elapsed + interval))
  done
  echo ""

  warn "Timeout reached ($UNLOAD_TIMEOUT_S s). llmworker (PID: $worker_pid) still holding $rss_mb MB."
  warn "Sending SIGKILL to enforce cleanup..."
  kill -9 "$worker_pid" 2>/dev/null || true
  sleep 2 # Let OS reclaim pages
  success "llmworker process terminated. RAM forcefully reclaimed."
}

cmd_load() {
  if [[ $# -eq 0 ]]; then
    error "Missing model identifier for 'load'."
    echo "Usage: $0 load <model-key> [options]"
    exit 1
  fi
  
  step "Loading model: $1"
  # Wrap the original command, strict pass-through
  if lms load "$@"; then
    success "Model loaded successfully."
  else
    error "Failed to load model '$1'."
    exit 1
  fi
}

cmd_health() {
  step "Checking LM Studio health"
  if lms server status &>/dev/null; then
    success "LM Studio Server is healthy and running."
    lms server status
  else
    warn "LM Studio Server might not be running or accessible."
    exit 1
  fi
}

cmd_server_restart() {
  step "Restarting LM Studio server"
  info "Stopping server..."
  lms server stop || true
  sleep 2
  info "Starting server..."
  lms server start
  success "LM Studio Server restarted."
}

cmd_help() {
  divider
  echo -e "${BOLD}Arkon LM Studio CLI Controller (lms-ctl)${RESET}"
  echo "A robust, fully-featured wrapper for 'lms' with strict resource enforcement."
  divider
  echo ""
  echo -e "${BOLD}Arkon Enhanced Commands:${RESET}"
  echo "  load [model-key] [opts]  Load a model (strict pass-through)"
  echo "  unload [identifier|-a]   Unload a model and ENFORCE RAM cleanup (SIGKILL if needed)"
  echo "  health                   Check if local LM Studio server is responding"
  echo "  server-restart           Force stop and start the local server"
  echo ""
  echo -e "${BOLD}Wrapped LM Studio Commands (Transparent pass-through):${RESET}"
  echo "  chat, get, ls, ps, import, server, log, link, runtime, clone, push, dev, login, logout, whoami"
  echo ""
  echo "Run '$0 <command> --help' for specific command options."
}

# ---------------------------------------------------------------------------
# Main Router
# ---------------------------------------------------------------------------
main() {
  check_prereqs

  if [[ $# -eq 0 ]]; then
    cmd_help
    exit 0
  fi

  local cmd="$1"
  shift

  case "$cmd" in
    load)
      cmd_load "$@"
      ;;
    unload)
      cmd_unload "$@"
      ;;
    health)
      cmd_health
      ;;
    server-restart)
      cmd_server_restart
      ;;
    help|--help|-h)
      cmd_help
      ;;
    # Pass-through for standard lms commands
    chat|get|ls|ps|import|server|log|link|runtime|clone|push|dev|login|logout|whoami)
      step "Running lms $cmd ${*:-}"
      lms "$cmd" "$@"
      ;;
    *)
      error "Unknown command: $cmd"
      cmd_help
      exit 1
      ;;
  esac
}

main "$@"
