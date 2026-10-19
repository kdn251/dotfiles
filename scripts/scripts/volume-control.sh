#!/usr/bin/env bash
# Change audio independently of the OSD daemon's audio connection.
set -euo pipefail
export LC_ALL=C
case "${1:-}" in
    raise) wpctl set-volume --limit 1.0 @DEFAULT_AUDIO_SINK@ 5%+ ;;
    lower) wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%- ;;
    mute-toggle) wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle ;;
    *) exit 2 ;;
esac
status=$(wpctl get-volume @DEFAULT_AUDIO_SINK@)
progress=$(awk '{v=$2; printf "%.4f\n", (v>1?1:v)}' <<< "$status")
icon=audio-volume-high-symbolic
label=""
if [[ "$status" == *MUTED* ]]; then
    icon=audio-volume-muted-symbolic
    label="Muted"
fi
# Display failure must never prevent volume control.
timeout 2s swayosd-client --custom-icon "$icon" --custom-progress "$progress" --custom-progress-text "$label" >/dev/null 2>&1 || true
