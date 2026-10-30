"""Exercise real MPV IPC with local media; no network or desktop window."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('reuse', ROOT / 'twitch-player-ipc.py')
reuse = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reuse)


class StreamReuseTests(unittest.TestCase):
    def test_cross_platform_loads_preserve_player_and_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            reuse.SOCKET = str(Path(tmp) / 'mpv.sock')
            video = str(Path(tmp) / 'sample.mkv')
            subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=black:s=32x32:d=10', '-c:v', 'ffv1', video], check=True)
            player = subprocess.Popen(['mpv', '--no-config', '--vo=null', '--ao=null',
                                       '--idle=yes', '--input-ipc-server=' + reuse.SOCKET,
                                       '--script=' + str(ROOT / 'twitch-first-frame.lua')],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic() + 5
                while not Path(reuse.SOCKET).exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                for service in ('Twitch', 'Kick', 'YouTube', 'Rumble', 'Twitch'):
                    connection, pid = reuse.connect()
                    with connection, connection.makefile('rwb', buffering=0) as stream:
                        reuse.command(stream, 'set_property', 'video-margin-ratio-right', .2)
                    self.assertEqual(reuse.reuse('example', service, video, '', '', service), player.pid)
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        connection, pid = reuse.connect()
                        with connection, connection.makefile('rwb', buffering=0) as stream:
                            actual = reuse.command(stream, 'get_property', 'user-data/stream-service')
                            try:
                                position = reuse.command(stream, 'get_property', 'time-pos') if actual == service else None
                            except ValueError:
                                position = None
                            margin = reuse.command(stream, 'get_property', 'video-margin-ratio-right')
                        if actual == service and position is not None:
                            break
                        time.sleep(.02)
                    self.assertEqual(actual, service)
                    self.assertIsNotNone(position)
                    self.assertEqual(margin, .2)
                    self.assertEqual(pid, player.pid)
            finally:
                player.terminate()
                player.wait(timeout=5)
