#!/bin/bash
# pip-hide-toggle.sh  (mod+H)
#
# Hide/unhide every picture-in-picture window by parking it on the
# special:mpvhidden workspace. Covers:
#   * mpv floats (twitch-launcher.sh, mpv-picker.sh, ...)
#   * Brave/Chromium PiP windows (YouTube, Jellyfin on turing:8096, ...) --
#     Chromium titles these "Picture in picture" regardless of the site.
#
# Gotchas handled here (verified on Hyprland 0.56):
#   * movetoworkspace(silent) on a PINNED window is a silent no-op, and the
#     Brave PiP windowrules pin it on open. So we unpin before hiding, remember
#     which addresses were pinned, and re-pin them on restore.
#   * Brave's PiP shares its pid with every other Brave window, so we address
#     windows by .address, never pid: (the old mpv-only bind used pid:).
#
# Same PiP filter as restore-pip-position.sh.

set -u

PIP_FILTER='.class=="mpv" or (.title|test("^Picture[- ]in[- ]Picture$";"i"))'
STATE="${XDG_RUNTIME_DIR:-/tmp}/pip-hidden-pinned"   # addresses to re-pin on restore
HIDDEN_WS="special:mpvhidden"

# A disabled video track destroys mpv's window when force-window=no. Restore
# it over IPC before inspecting windows, and treat this press as an unhide.
recovered=$(python3 - <<'PY'
import json
import socket

try:
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        client.connect('/tmp/mpv-yt-ipc')
        with client.makefile('r') as replies:
            def command(*args):
                client.sendall((json.dumps({'command': args, 'request_id': 1}) + '\n').encode())
                while True:
                    line = replies.readline()
                    if not line:
                        raise OSError('mpv disconnected')
                    reply = json.loads(line)
                    if reply.get('request_id') == 1:
                        if reply.get('error') != 'success':
                            raise OSError(reply.get('error'))
                        return reply.get('data')

            if command('get_property', 'vid') is False:
                tracks = command('get_property', 'track-list')
                if any(track.get('type') == 'video' for track in tracks):
                    command('set_property', 'vid', 'auto')
                    print('yes')
except (OSError, ValueError):
    pass  # No reachable mpv: retain the normal PiP window toggle.
PY
)

# address \t workspace \t pinned  for every PiP window
mapfile -t ROWS < <(hyprctl clients -j | jq -r "
  .[] | select($PIP_FILTER)
  | [ .address, .workspace.name, (.pinned|tostring) ] | @tsv")

[ "${#ROWS[@]}" -gt 0 ] || exit 0

hidden=()  visible=()  visible_pinned=()
for row in "${ROWS[@]}"; do
  IFS=$'\t' read -r addr ws pinned <<<"$row"
  if [ "$ws" = "$HIDDEN_WS" ]; then
    hidden+=("$addr")
  else
    visible+=("$addr")
    [ "$pinned" = "true" ] && visible_pinned+=("$addr")
  fi
done

batch=""
if [ "${#hidden[@]}" -gt 0 ]; then
  # --- RESTORE: bring every hidden PiP back to the current workspace ---
  repin=""
  [ -r "$STATE" ] && repin=$(<"$STATE")
  for addr in "${hidden[@]}"; do
    batch+="dispatch movetoworkspace e+0,address:$addr; "
    # pin is a toggle; these windows are unpinned (we unpinned them), so one
    # toggle == pin. Only re-pin what was pinned before we hid it.
    if grep -qx "$addr" <<<"$repin"; then
      batch+="dispatch pin address:$addr; "
    fi
  done
  rm -f "$STATE"
else
  # Re-enabling video was this press's restore action. Do not immediately
  # hide the newly created window (or any other visible PiP windows).
  [ "$recovered" = "yes" ] && exit 0
  # --- HIDE: unpin (if needed) then park on the special workspace ---
  printf '%s\n' "${visible_pinned[@]}" > "$STATE"
  for addr in "${visible_pinned[@]}"; do
    batch+="dispatch pin address:$addr; "        # toggle -> unpinned
  done
  for addr in "${visible[@]}"; do
    batch+="dispatch movetoworkspacesilent $HIDDEN_WS,address:$addr; "
  done
fi

hyprctl --batch "$batch" >/dev/null
