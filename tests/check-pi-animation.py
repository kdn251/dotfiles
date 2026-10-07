#!/usr/bin/env python3
"""Offline real-Pi animation smoke test. Requires pi and tmux, no model login."""
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import uuid

root = Path(__file__).resolve().parents[1]
session = "pi-animation-test-" + uuid.uuid4().hex[:10]
with tempfile.TemporaryDirectory() as temporary:
    agent = Path(temporary) / "agent"
    agent.mkdir()
    (agent / "calm.json").write_text(json.dumps({"enabled": True}))
    command = shlex.join([
        "env", f"PI_CODING_AGENT_DIR={agent}", "pi", "--offline", "--no-approve",
        "--no-extensions", "--no-skills", "--no-prompt-templates", "--no-session",
        "-e", str(root / "tests/pi-animation-fixture.ts"),
    ]) + "; sleep 10"
    subprocess.run(["tmux", "new-session", "-d", "-s", session, "-x", "100", "-y", "40", command], check=True)
    try:
        time.sleep(2)
        subprocess.run(["tmux", "send-keys", "-t", session, "-l", "/test-animation"], check=True)
        subprocess.run(["tmux", "send-keys", "-t", session, "Enter"], check=True)
        deadline = time.monotonic() + 15
        output = ""
        while time.monotonic() < deadline:
            output = subprocess.check_output(["tmux", "capture-pane", "-p", "-t", session], text=True)
            if "ANIMATION_TEST_PASS" in output:
                print("PASS: real Pi widget lifecycle, first-text handoff, preview cancellation, off mode, and pixel bounds.")
                break
            if "ANIMATION_TEST_FAIL" in output or "uncaughtException" in output or "Failed to load" in output:
                raise RuntimeError(output)
            time.sleep(0.2)
        else:
            raise RuntimeError("Timed out waiting for the animation fixture:\n" + output)
    finally:
        subprocess.run(["tmux", "kill-session", "-t", session], check=False)
