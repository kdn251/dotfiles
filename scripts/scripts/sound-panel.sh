#!/bin/bash
# Waybar sound quick controls, using the same notification panels as Wi-Fi.
export LC_ALL=C
source "$HOME/scripts/panel-guard.sh"
panel_guard sound

fail() {
  notify-send -a "Sound" -u normal -t 3000 "Sound" "Could not update audio. Open All settings to check the device."
}

while true; do
  sinks=$(pactl -f json list sinks) || { fail; exit 1; }
  default=$(pactl get-default-sink)
  current=$(jq -c --arg name "$default" '.[] | select(.name == $name)' <<<"$sinks")
  args=()
  names=()
  if [ -n "$current" ]; then
    description=$(jq -r '.description | @html' <<<"$current")
    volume=$(jq '[.volume[].value] | max / 65536 * 100 | round' <<<"$current")
    muted=$(jq -r '.mute' <<<"$current")
    mute_label="Mute output"
    status="${volume}%"
    if [ "$muted" = true ]; then
      mute_label="Unmute output"
      status="${volume}% (muted)"
    fi
    body=$(printf 'Output  <b>%s</b>\nVolume  <b>%s</b>' "$description" "$status")
    args+=(-A "down=Volume −" -A "up=Volume +" -A "mute=$mute_label")
    while IFS= read -r name; do names+=("$name"); done < <(jq -r '.[].name' <<<"$sinks")
    # Offer output switching only when more than one device is available.
    if [ "${#names[@]}" -gt 1 ]; then
      for i in "${!names[@]}"; do
        label=$(jq -r --arg name "${names[$i]}" '.[] | select(.name == $name) | .description' <<<"$sinks")
        label=${label:0:36}
        [ "${names[$i]}" = "$default" ] && label+=" ✓"
        args+=(-A "output$i=$label")
      done
    fi
  else
    body="No audio output available."
  fi

  source_name=$(pactl get-default-source 2>/dev/null)
  mic_state=$(pactl get-source-mute "$source_name" 2>/dev/null)
  if [ -n "$mic_state" ]; then
    if [[ "$mic_state" == *yes ]]; then
      body+=$'\nMicrophone  <b>muted</b>'
      args+=(-A "mic=Unmute microphone")
    else
      body+=$'\nMicrophone  <b>on</b>'
      args+=(-A "mic=Mute microphone")
    fi
  fi
  args+=(-A "settings=All settings…")
  action=$(panel_notify -a "Sound" -u low -t 15000 "Sound" "$body" "${args[@]}")
  case "$action" in
    down)
      next=$((volume - 5)); ((next < 0)) && next=0
      pactl set-sink-volume "$default" "$next%" || { fail; exit 1; }
      ;;
    up)
      next=$((volume + 5)); ((next > 100)) && next=100
      pactl set-sink-volume "$default" "$next%" || { fail; exit 1; }
      ;;
    mute) pactl set-sink-mute "$default" toggle || { fail; exit 1; } ;;
    mic) pactl set-source-mute "$source_name" toggle || { fail; exit 1; } ;;
    output*)
      idx=${action#output}
      [[ "$idx" =~ ^[0-9]+$ ]] && [ -n "${names[$idx]:-}" ] || exit 1
      target=${names[$idx]}
      pactl set-default-sink "$target" || { fail; exit 1; }
      # Move existing playback as well as changing the destination for new audio.
      while read -r input; do
        pactl move-sink-input "$input" "$target" 2>/dev/null
      done < <(pactl -f json list sink-inputs | jq -r '.[].index')
      ;;
    settings)
      # Release the panel lock before starting a long-lived settings window.
      exec 9>&-
      exec pavucontrol
      ;;
    *) exit 0 ;;
  esac
  # Refresh the panel after each quick action, allowing repeated adjustments.
done
