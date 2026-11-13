#!/usr/bin/env python3
"""Feed Hex's live dictation state to Waybar."""
import json
import subprocess
import time


def get_state():
    try:
        result = subprocess.run(["hex", "status", "--json"], capture_output=True,
                                text=True, timeout=2, check=True)
        status = json.loads(result.stdout)
        capture = status.get("capture", {})
        listener = status.get("listener", {})
        if capture.get("state") == "recording":
            return "recording"
        if capture.get("pending_jobs", 0) or capture.get("state") in ("transcribing", "processing"):
            return "transcribing"
        if "transcrib" in listener.get("status", "").lower():
            return "transcribing"
        return "idle" if listener.get("running") else "stopped"
    except (OSError, ValueError, subprocess.SubprocessError):
        return "stopped"


def main():
    previous = None
    while True:
        state = get_state()
        if state != previous:
            print(json.dumps({"text": "", "alt": state, "class": state,
                              "tooltip": "Hex: " + state}), flush=True)
            previous = state
        time.sleep(0.2 if state != "stopped" else 1)


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
