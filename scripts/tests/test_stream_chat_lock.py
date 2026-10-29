import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

class LockTests(unittest.TestCase):
    def test_chat_process_does_not_keep_transition_lock(self):
        source=(SCRIPTS/'twitch-launcher.sh').read_text()
        helper=source[source.index('chat_start() {'):source.index('# Serialize chat transitions')]
        with tempfile.TemporaryDirectory() as d:
            script='''
chat_stop() { :; }
stream_session_current() { return 0; }
chatterino() { sleep 1; }
CHAT_LAYOUT="$XDG_RUNTIME_DIR/layout.json"
'''+helper+'''
(
 exec 8>"$XDG_RUNTIME_DIR/lock"
 flock 8
 chat_start example
)
flock -w .2 "$XDG_RUNTIME_DIR/lock" true
'''
            result=subprocess.run(['bash','-c',script],env=dict(os.environ,XDG_RUNTIME_DIR=d),capture_output=True,timeout=4)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((Path(d)/f'twitch-chat-channel-{os.getuid()}').read_text().strip(),'example')

if __name__=='__main__':unittest.main()
