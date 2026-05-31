#!/usr/bin/env bash
# Helper wrapper to run regen-failed-source.py inside the arkon_worker container
set -euo pipefail

SOURCE_ID="${1:-}"

if [[ -z "$SOURCE_ID" ]]; then
  echo "No <source_id> provided. Fetching recent sources from database..."
  
  # Fetch recent sources: id|status|title
  DB_OUT=$(docker exec arkon_postgres psql -U arkon -d arkon -tAc "SELECT id, status, title FROM sources ORDER BY created_at DESC LIMIT 20;" 2>/dev/null || true)
  
  if [[ -z "$DB_OUT" ]]; then
    echo "No sources found or failed to connect to database." >&2
    exit 1
  fi
  
  declare -a ids=()
  declare -a displays=()
  
  while IFS='|' read -r id status title; do
    [[ -z "$id" ]] && continue
    ids+=("$id")
    displays+=("[$status] $title")
  done <<< "$DB_OUT"
  
  echo "Please select a source to regenerate:"
  for i in "${!displays[@]}"; do
    printf "  %2d) %s\n" "$((i+1))" "${displays[$i]}"
  done
  
  echo
  read -rp "Enter number (1-${#displays[@]}): " choice
  
  if ! [[ "$choice" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#displays[@]} )); then
    echo "Invalid selection." >&2
    exit 1
  fi
  
  SOURCE_ID="${ids[$((choice-1))]}"
  echo "Selected Source ID: $SOURCE_ID"
  echo
fi

cat "$(dirname "$0")/regen-failed-source.py" | docker exec -i arkon_worker python - "$SOURCE_ID"
