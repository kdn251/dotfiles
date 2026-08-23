#!/bin/bash
# pip-mute-toggle.sh  (mod+M)
#
# Mute/unmute whatever is playing picture-in-picture:
#   * mpv          -> playerctl volume 0 / 1 (unchanged from the old inline bind)
#   * Brave PiP    -> toggle mute on Brave's PulseAudio/PipeWire sink-input(s).
#                     Chromium's MPRIS player ignores Volume writes (verified:
#                     `playerctl -p brave.* volume 0` reads back 1.0), so we
#                     go through pactl instead. Note this mutes ALL Brave audio
#                     (Chromium tags every stream media.name="Playback", so
#                     per-tab isn't distinguishable) -- fine for PiP use.
#
# Brave is only touched when a Chromium PiP window actually exists, so mod+M
# with no PiP open (e.g. just a YouTube tab) does nothing, like before.

set -u

# --- mpv ---
if pgrep -x mpv >/dev/null; then
  vol=$(playerctl --player=mpv volume 2>/dev/null | cut -d. -f1)
  if [ "${vol:-0}" -gt 0 ]; then
    playerctl --player=mpv volume 0.0
  else
    playerctl --player=mpv volume 1.0
  fi
fi

# --- Brave / Chromium PiP (YouTube, Jellyfin, ...) ---
if hyprctl clients -j | jq -e '
     [.[] | select(.title|test("^Picture[- ]in[- ]Picture$";"i"))] | length > 0' >/dev/null; then
  # index \t muted for every Brave/Chromium sink-input
  mapfile -t inputs < <(pactl -f json list sink-inputs | jq -r '
    .[] | select((.properties["application.process.binary"] // "")
                 | test("^(brave|chromium|chrome|google-chrome)")
                 or (.properties["application.name"] // "" | test("^(Brave|Chromium|Google Chrome)")))
        | [ (.index|tostring), (.mute|tostring) ] | @tsv')
  [ "${#inputs[@]}" -gt 0 ] || exit 0

  # If anything is audible -> mute everything; else unmute everything.
  target=1
  for row in "${inputs[@]}"; do
    IFS=$'\t' read -r idx muted <<<"$row"
    [ "$muted" = "false" ] && { target=1; break; }
    target=0
  done
  for row in "${inputs[@]}"; do
    IFS=$'\t' read -r idx muted <<<"$row"
    pactl set-sink-input-mute "$idx" "$target"
  done
fi
