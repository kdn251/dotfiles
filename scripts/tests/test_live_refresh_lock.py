"""Notification action workers must not keep the live-list refresh locked."""
import fcntl
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import unittest

SCRIPT=Path(__file__).parents[1]/'scripts/update-live-list.sh'

class LiveRefreshLockTests(unittest.TestCase):
    def test_detached_notification_does_not_inherit_refresh_lock(self):
        invocation=next(line for line in SCRIPT.read_text().splitlines()
                        if line.startswith('"$HOME/scripts/twitch-golive-notify.sh"'))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'scripts').mkdir()
            notifier=root/'scripts/twitch-golive-notify.sh'
            notifier.write_text('#!/bin/bash\nsleep 30 &\necho $! > "$HOME/worker"\n')
            notifier.chmod(0o700)
            command='exec 9>"$HOME/refresh.lock"\nflock 9\n'+invocation
            process=subprocess.Popen(['bash','-c',command],env=dict(os.environ,HOME=directory),
                                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            try:
                process.wait(timeout=3)
                pid=int((root/'worker').read_text())
                os.kill(pid,0)  # action worker is still running
                with (root/'refresh.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:
                try:os.killpg(process.pid,signal.SIGTERM)
                except ProcessLookupError:pass
