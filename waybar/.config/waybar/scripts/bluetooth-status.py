#!/usr/bin/env python3
"""Avoid a second Bluetooth icon when the audio icon already represents it."""
import html
import json
import os
from pathlib import Path
import subprocess
import sys


def bluetooth_audio():
    try:
        sink = subprocess.check_output(['pactl', 'get-default-sink'], text=True,
                                       stderr=subprocess.DEVNULL, timeout=2)
        return sink.strip().startswith('bluez_')
    except (OSError, subprocess.SubprocessError):
        return False


def status():
    if bluetooth_audio():
        return {'text': ''}
    from gi.repository import Gio
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        objects = bus.call_sync(
            'org.bluez', '/', 'org.freedesktop.DBus.ObjectManager',
            'GetManagedObjects', None, None, Gio.DBusCallFlags.NONE, 2000, None
        ).unpack()[0]
        lines = []
        powered = False
        for interfaces in objects.values():
            adapter = interfaces.get('org.bluez.Adapter1', {})
            if adapter:
                powered |= adapter.get('Powered', False)
                lines.append(adapter.get('Alias', 'Bluetooth'))
            device = interfaces.get('org.bluez.Device1', {})
            if device.get('Connected'):
                name = device.get('Alias', 'Connected device')
                battery = interfaces.get('org.bluez.Battery1', {}).get('Percentage')
                lines.append(f'{name} ({battery}%)' if battery is not None else name)
        if not powered:
            lines.append('Bluetooth off')
        return {'text': '', 'tooltip': html.escape('\n'.join(lines) or 'Bluetooth'),
                'class': 'on' if powered else 'off'}
    except Exception:
        return {'text': '', 'tooltip': 'Bluetooth settings'}


if __name__ == '__main__':
    if sys.argv[1:] == ['--click-audio']:
        panel = 'bluetooth-panel.sh' if bluetooth_audio() else 'sound-panel.sh'
        os.execv(str(Path.home() / 'scripts' / panel), [panel])
    print(json.dumps(status()))
