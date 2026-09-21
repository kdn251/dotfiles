#!/usr/bin/env python3
"""Wait for this particular mpv launch before Newsboat marks its item read."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def play(args):
    with tempfile.TemporaryDirectory(prefix='newsboat-play-') as directory:
        ready = Path(directory) / 'ready'
        env = dict(os.environ, NEWSBOAT_PLAY_READY=str(ready))
        launcher = Path(__file__).with_name('mpv-yt')
        process = subprocess.Popen([str(launcher), *args], env=env, start_new_session=True,
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
        end = time.monotonic() + 30
        while time.monotonic() < end:
            if ready.exists():
                result = ready.read_text()
                if result == 'playing':
                    subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-history.py')),
                                    'record', args[0], 'video'], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL)
                    return 0
                if result == 'failed':
                    break
            if process.poll() not in (None, 0):
                break
            time.sleep(0.05)
    subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '5000',
                    'Playback did not start', 'Read status was not changed.'])
    return 1


if __name__ == '__main__':
    sys.exit(play(sys.argv[1:]))
