"""Stream replacements must not report the old player's exit as a failure."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

class SessionTests(unittest.TestCase):
    def test_exit_notifications_belong_only_to_current_session(self):
        source=(SCRIPTS/'twitch-launcher.sh').read_text()
        helpers=source[source.index('stream_session_current()'):source.index('# --- Chatterino lifecycle')]
        for rc,replaced,expected in [(1,False,True),(1,True,False),(143,False,False),(143,True,False),(0,False,False)]:
            with self.subTest(rc=rc,replaced=replaced),tempfile.TemporaryDirectory() as d:
                root=Path(d)
                script=helpers+'''
SESSION_FILE="$ROOT/session"
SESSION_ID=old
NOTIFY_ARGS=(-a Kick)
STREAMER=example
SERVICE=Kick
printf old > "$SESSION_FILE"
notify-send() { printf notified > "$ROOT/notification"; }
mpv() {
 if [ "$REPLACED" = yes ]; then printf new > "$SESSION_FILE"; fi
 return "$RC"
}
play_live_stream dummy
'''
                subprocess.run(['bash','-c',script],env=dict(os.environ,ROOT=d,RC=str(rc),REPLACED='yes' if replaced else 'no'),check=False)
                self.assertEqual((root/'notification').exists(),expected)
