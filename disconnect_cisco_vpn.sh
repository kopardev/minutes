#!/usr/bin/env bash
set -euo pipefail

# Disconnect Cisco Secure Client / AnyConnect on macOS.
# Usage: ./disconnect_cisco_vpn.sh

STATE_FILE="${HOME}/.cisco_last_vpn_endpoint"

find_cisco_cli() {
  local candidates=(
    "/opt/cisco/secureclient/bin/vpn"
    "/opt/cisco/anyconnect/bin/vpn"
    "/opt/cisco/secureclient/bin/vpncli"
    "/opt/cisco/anyconnect/bin/vpncli"
  )

  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      echo "$c"
      return 0
    fi
  done

  # Fallback to PATH
  if command -v vpn >/dev/null 2>&1; then
    command -v vpn
    return 0
  fi
  if command -v vpncli >/dev/null 2>&1; then
    command -v vpncli
    return 0
  fi

  return 1
}

is_vpn_routed() {
  route -n get default 2>/dev/null | grep -q 'interface: utun'
}

extract_endpoint() {
  # Cisco state output varies by client version, often prefixed with ">>".
  awk -F': *' '
    /^[[:space:]]*(>>[[:space:]]*)?([Ss]erver|[Vv][Pp][Nn][[:space:]]+[Ss]erver|[Hh]ost|[Gg]ateway)[[:space:]]*:/ {
      print $2
      exit
    }
  '
}

echo "[INFO] Checking Cisco CLI..."
if ! CLI="$(find_cisco_cli)"; then
  echo "[ERROR] Cisco CLI not found (vpn/vpncli)."
  exit 1
fi
echo "[INFO] Using CLI: $CLI"

echo "[INFO] VPN state (before):"
STATE_BEFORE="$($CLI state 2>/dev/null || true)"
echo "$STATE_BEFORE"

LAST_ENDPOINT="$(printf '%s\n' "$STATE_BEFORE" | extract_endpoint || true)"
if [[ -n "$LAST_ENDPOINT" ]]; then
  printf '%s\n' "$LAST_ENDPOINT" > "$STATE_FILE"
  echo "[INFO] Saved last endpoint to $STATE_FILE"
else
  echo "[INFO] Endpoint not present in current state output; state file unchanged."
fi

if is_vpn_routed; then
  echo "[INFO] Default route is currently via utun (VPN likely active)."
else
  echo "[INFO] Default route is not via utun."
fi

echo "[INFO] Disconnecting..."
"$CLI" disconnect || true

sleep 2

echo "[INFO] VPN state (after):"
"$CLI" state || true

if is_vpn_routed; then
  echo "[WARN] Still routed via utun. VPN may be reconnecting automatically."
  exit 2
else
  echo "[OK] VPN appears disconnected."
fi
