#!/usr/bin/env bash
# Waybar feeder for Handy (speech-to-text). Replaces `voxtype status --follow`.
# Handy has no status CLI, so we tail its log and translate state transitions
# into the same JSON classes the old voxtype module used (recording/transcribing/idle),
# keeping the existing #custom-handy CSS (red pulse while recording).

# Re-exec under stdbuf so stdout is line-buffered; otherwise bash's printf to
# waybar's pipe is block-buffered and the icon won't update until ~4KB accumulates.
if [ -z "$_HANDY_LINEBUF" ]; then
  export _HANDY_LINEBUF=1
  exec stdbuf -oL "$0" "$@"
fi

LOG="$HOME/.local/share/com.pais.handy/logs/handy.log"
state=""

emit() {
  local s=$1 tip
  case $s in
    recording)    tip="Handy: recording";;
    transcribing) tip="Handy: transcribing";;
    *)            s=idle; tip="Handy: idle";;
  esac
  # text empty: waybar renders {icon} from format-icons keyed on "alt"; "class" drives CSS.
  printf '{"text":"","alt":"%s","class":"%s","tooltip":"%s"}\n' "$s" "$s" "$tip"
}

emit idle

# Resilient follow loop: never exits on its own (an idle Handy logs nothing, so
# the read timeout must NOT end the loop), and restarts tail if Handy rotates or
# recreates its log on restart.
while true; do
  # Wait for the log file to appear (Handy may not be running yet at login).
  while [ ! -f "$LOG" ]; do sleep 2; done
  state=idle
  # Follow only new lines (-n0).
  tail -Fn0 "$LOG" 2>/dev/null | while true; do
    IFS= read -r -t 6 line
    rc=$?
    if [ "$rc" -gt 128 ]; then
      # read timed out: watchdog so "transcribing" can't stick if a completion
      # line is ever missed. recording stays until an explicit stop event.
      [ "$state" = transcribing ] && { state=idle; emit idle; }
      continue
    elif [ "$rc" -ne 0 ]; then
      break   # EOF: tail ended (log rotated / Handy restarted) -> respawn it
    fi
    case $line in
      *"TranscribeAction::start called"*) [ "$state" != recording ]    && { state=recording;    emit recording; } ;;
      *"TranscribeAction::stop called"*)  [ "$state" != transcribing ] && { state=transcribing; emit transcribing; } ;;
      *"skipping persistence"*|*"Transcription complete"*|*"CancelAction"*|*"cancel called"*)
        [ "$state" != idle ] && { state=idle; emit idle; } ;;
    esac
  done
  sleep 1
done
