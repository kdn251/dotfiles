#!/bin/bash

# --- DATA GATHERING ---
STATUS_JSON=$(tailscale status --json)

# FIX 1: Strip the CIDR mask (/32 or /128) from the Exit IP
CURRENT_EXIT_IP=$(echo "$STATUS_JSON" | jq -r '.ExitNodeStatus.TailscaleIPs[0] // empty' | cut -d'/' -f1 | xargs)

select_node() {
  # Get nodes and format as "hostname (IP)"
  mapfile -t DATA < <(tailscale exit-node list | grep "^[[:space:]]*100\." | awk '{print $2 " (" $1 ")"}')

  if [ ${#DATA[@]} -eq 0 ]; then
    notify-send "Tailscale" "No eligible exit nodes found."
    exit 1
  fi

  # Fuzzel selection
  CHOICE=$(printf "%s\n" "${DATA[@]}" | fuzzel --dmenu --prompt="Exit Node: " --width=40)

  if [ -n "$CHOICE" ]; then
    # Extract IP and ensure it's clean
    SELECTED_IP=$(echo "$CHOICE" | grep -oE "100\.[0-9]+\.[0-9]+\.[0-9]+" | xargs)

    # TOGGLE LOGIC
    if [[ "$SELECTED_IP" == "$CURRENT_EXIT_IP" ]]; then
      tailscale set --exit-node=""
      notify-send "Tailscale" "Exit node disabled."
    else
      tailscale set --exit-node="$SELECTED_IP"
      notify-send "Tailscale" "Routing through $SELECTED_IP"
    fi
  fi
}

# --- EXECUTION ---
if [ "$1" == "toggle" ]; then
  select_node
  exit 0
fi

# --- WAYBAR OUTPUT ---
if [ -n "$CURRENT_EXIT_IP" ]; then
  # Look up peer hostname by current IP (without the /32)
  FULL_NAME=$(echo "$STATUS_JSON" | jq -r --arg IP "$CURRENT_EXIT_IP" '.Peer[] | select(.TailscaleIPs[] == $IP) | .HostName')

  if [ -n "$FULL_NAME" ] && [ "$FULL_NAME" != "null" ]; then
    DISPLAY_NAME=$(echo "$FULL_NAME" | cut -d'.' -f1)
  else
    DISPLAY_NAME="boole"
  fi

  # Active State: Show icon + name
  echo "{\"text\": \"󰖂 $DISPLAY_NAME\", \"class\": \"active\", \"tooltip\": \"Exit Node: $FULL_NAME ($CURRENT_EXIT_IP)\"}"
else
  # Inactive State: Show the icon only (or "󰖂 Off") so you can still click it
  echo "{\"text\": \"󰖂\", \"class\": \"inactive\", \"tooltip\": \"Tailscale: No exit node\"}"
fi
