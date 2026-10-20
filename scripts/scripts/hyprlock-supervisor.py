#!/usr/bin/env python3
"""Run one lock attempt; systemd retries failures, but never normal unlocks.

Hyprlock can remain alive after a fatal Wayland protocol error. Detect that
explicit failure in stderr and kill only our child, leaving the compositor's
session lock intact. Never use SIGUSR1 (which would unlock the session).
"""
import os
import selectors
import subprocess
import sys

FATAL = (b"wl_display#", b"Disconnected from pollfd")

def main():
    child = subprocess.Popen(
        ["hyprlock", "--grace", "0", "--immediate-render", "--no-fade-in"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    selector = selectors.DefaultSelector()
    selector.register(child.stdout, selectors.EVENT_READ)
    pending = b""
    failed = False
    while selector.get_map():
        for key, _ in selector.select(timeout=1):
            data = os.read(key.fd, 65536)
            if not data:
                selector.unregister(key.fileobj)
                continue
            sys.stdout.buffer.write(data)
            sys.stdout.buffer.flush()
            pending += data
            lines = pending.split(b"\n")
            pending = lines.pop()
            for line in lines:
                if (FATAL[0] in line and b"error" in line) or FATAL[1] in line:
                    print("supervisor: fatal Wayland error; replacing broken lock client", flush=True)
                    failed = True
                    child.kill()
        if child.poll() is not None and not selector.get_map():
            break
    return 1 if failed or child.wait() != 0 else 0

if __name__ == "__main__":
    sys.exit(main())
