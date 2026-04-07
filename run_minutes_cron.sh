#!/bin/bash
set -euo pipefail

REPO_DIR="/Users/kopardevn/Documents/GitRepos/minutes"
LOG_DIR="$REPO_DIR/logs"
LOG_FILE="$LOG_DIR/cron.log"

mkdir -p "$LOG_DIR"
cd "$REPO_DIR"

# Load provider keys and folder IDs.
source "$REPO_DIR/export_this_first"

# Keep cron output format independent from interactive defaults in export_this_first.
CRON_SUMMARY_FORMAT="${CRON_SUMMARY_FORMAT:-pdf}"

# Disconnect Cisco VPN before running the Drive-backed cron job.
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Disconnecting Cisco VPN before cron run" >> "$LOG_FILE"
"$REPO_DIR/disconnect_cisco_vpn.sh" >> "$LOG_FILE" 2>&1 || true

# Run one cron-safe pass and append logs.
"$REPO_DIR/.venv/bin/python" -m minutes \
  --provider "${LLM_PROVIDER:-ollama}" \
  --start-ollama \
  --stop-ollama \
  --max-files 50 \
  --manifest "$REPO_DIR/manifest_cron.json" \
  --format "$CRON_SUMMARY_FORMAT" \
  --verbose \
  >> "$LOG_FILE" 2>&1
