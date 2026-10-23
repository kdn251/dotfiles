#!/usr/bin/env python3
"""Hide the local cursor after 3s only over a focused fullscreen stream."""
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess


def hypr(*args):
    return subprocess.check_output(['hyprctl', *args], text=True, timeout=3)


def eligible(window, pointer):
    if (window.get('class') != 'com.moonlight_stream.Moonlight'
            or not window.get('title', '').endswith(' - Moonlight')
            or window.get('fullscreen') not in (2, 3)):
        return False
    x, y = window['at']
    width, height = window['size']
    return x <= pointer['x'] < x + width and y <= pointer['y'] < y + height


def main():
    # The desktop default is explicitly 0 (never hide); don't inherit a stale
    # override if systemd restarts us after a crash while Moonlight is focused.
    previous = None
    def apply(value):
        nonlocal previous
        if value != previous:
            hypr('keyword', 'cursor:inactive_timeout', str(value))
            previous = value

    def stop(*_):
        raise SystemExit

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    path = (Path(os.environ['XDG_RUNTIME_DIR']) / 'hypr'
            / os.environ['HYPRLAND_INSTANCE_SIGNATURE'] / '.socket2.sock')
    try:
        with socket.socket(socket.AF_UNIX) as events:
            events.connect(str(path))
            while True:
                window = json.loads(hypr('activewindow', '-j'))
                pointer = json.loads(hypr('cursorpos', '-j'))
                apply(3 if eligible(window, pointer) else 0)
                # Focus/workspace/fullscreen events take effect immediately;
                # polling also catches the pointer moving to another display.
                if select.select([events], [], [], 0.5)[0]:
                    data = events.recv(65536)
                    if not data:
                        break
                    if b'configreloaded>>' in data:
                        previous = None
    finally:
        try:
            hypr('keyword', 'cursor:inactive_timeout', '0')
        except (OSError, subprocess.SubprocessError):
            pass


if __name__ == '__main__':
    main()
