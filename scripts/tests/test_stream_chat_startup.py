"""Chat setup must not hold up playback or run for a superseded selection."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

class ChatStartupTests(unittest.TestCase):
    def test_background_chat_and_stale_worker(self):
        source=(Path(__file__).resolve().parents[1]/'scripts/twitch-launcher.sh').read_text()
        helper=source[source.index('manage_chat() ('):source.index('# --- 1. Setup')]
        with tempfile.TemporaryDirectory() as tmp:
            code='''
stream_session_current() { [ "$(cat "$XDG_RUNTIME_DIR/session")" = "$SESSION_ID" ]; }
chat_stop() { touch "$XDG_RUNTIME_DIR/chat-started"; sleep .2; touch "$XDG_RUNTIME_DIR/chat-done"; }
printf first > "$XDG_RUNTIME_DIR/session"
SESSION_ID=first
'''+helper+'''
manage_chat stop &
worker=$!
# The playback path can proceed while chat is still closing.
test ! -e "$XDG_RUNTIME_DIR/chat-done" || exit 1
wait "$worker"
test -e "$XDG_RUNTIME_DIR/chat-done" || exit 2
rm "$XDG_RUNTIME_DIR/chat-started"
printf second > "$XDG_RUNTIME_DIR/session"
manage_chat stop
test ! -e "$XDG_RUNTIME_DIR/chat-started" || exit 3
'''
            subprocess.run(['bash','-c',code],env=dict(os.environ,XDG_RUNTIME_DIR=tmp),check=True,timeout=4)

if __name__=='__main__':unittest.main()
