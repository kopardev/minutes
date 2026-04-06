#!/bin/bash
set -euo pipefail

REPO_DIR="/Users/kopardevn/Documents/GitRepos/minutes"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

# Load provider keys and folder IDs.
source "$REPO_DIR/export_this_first"

# Run one cron-safe pass and append logs.
"$REPO_DIR/.venv/bin/python" -m minutes \
  --provider "${LLM_PROVIDER:-ollama}" \
  --start-ollama \
  --stop-ollama \
  --max-files 50 \
  --manifest "$REPO_DIR/manifest_cron.json" \
  --format "${SUMMARY_FORMAT:-pdf}" \
  --verbose \
  >> "$LOG_FILE" 2>&1
