"""Star commands return while HTTP is blocked and preserve request order."""
import http.server
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/newsboat-starred.py'

class AsyncStarTests(unittest.TestCase):
    def test_commands_return_before_network_and_apply_in_order(self):
        started = threading.Event()
        release = threading.Event()
        changes = []
        row = dict(id=1, url='https://example.com/item', title='Item',
                   feed={'title': 'Source'}, status='unread', starred=False)
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                data = ({'total': int(row['starred']), 'entries': [row] if row['starred'] else []}
                        if '?' in self.path else row)
                self.send_response(200); self.end_headers()
                self.wfile.write(json.dumps(data).encode())
            def do_PUT(self):
                data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                started.set()
                release.wait(8)
                row['starred'] = data['starred']
                changes.append(row['starred'])
                self.send_response(204); self.end_headers()
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                creds = root/'creds'
                creds.write_text(f'miniflux-url "http://127.0.0.1:{server.server_port}"\nminiflux-login test\nminiflux-password test\n')
                cache = root/'cache'
                with sqlite3.connect(cache) as db:
                    db.execute('CREATE TABLE rss_item(guid TEXT, url TEXT)')
                    db.execute('INSERT INTO rss_item VALUES (?,?)', ('1', row['url']))
                env = dict(os.environ, XDG_STATE_HOME=directory, NEWSBOAT_CACHE=str(cache),
                           NEWSBOAT_URLS_FILE=str(root/'urls'), NEWSBOAT_MINIFLUX_CONFIG=str(creds))
                try:
                    subprocess.run([sys.executable, str(SCRIPT), 'save', row['url']],
                                   env=env, check=True, timeout=2, capture_output=True)
                    self.assertTrue(started.wait(2))
                    self.assertEqual(changes, [])
                    subprocess.run([sys.executable, str(SCRIPT), 'remove', row['url']],
                                   env=env, check=True, timeout=2, capture_output=True)
                    self.assertEqual(changes, [])
                finally:
                    release.set()
                deadline = time.monotonic()+5
                queue = root/'newsboat/star-actions'
                while time.monotonic()<deadline:
                    if changes == [True, False] and not list(queue.glob('*.json')): break
                    time.sleep(.02)
                self.assertEqual(changes, [True, False])
                self.assertEqual(list(queue.glob('*.json')), [])
                self.assertEqual((root/'newsboat/starred-urls.txt').read_text(), '')
        finally:
            release.set(); server.shutdown(); server.server_close(); thread.join()
