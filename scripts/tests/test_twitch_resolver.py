import multiprocessing
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import twitch_resolver as resolver


def fake_fetch(name, session):
    if name == 'offline':
        raise ValueError('private upstream details')
    return {'streams': {'best': {'url': 'https://example.test/' + name}},
            'session': id(session)}


class ResolverTests(unittest.TestCase):
    def test_resident_requests_reuse_session_and_isolate_failures(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, XDG_RUNTIME_DIR=tmp), \
                patch.object(resolver, 'load_fetch', return_value=fake_fetch):
            process = multiprocessing.get_context('fork').Process(target=resolver.serve)
            process.start()
            try:
                sock = Path(tmp) / 'twitch-stream-urls/resolver.sock'
                deadline = time.monotonic() + 5
                while not sock.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(sock.exists())
                first = resolver.request('first')
                second = resolver.request('second')
                self.assertEqual(first['session'], second['session'])
                self.assertTrue(second['streams']['best']['url'].endswith('/second'))
                with self.assertRaisesRegex(ValueError, '^Resolution failed$'):
                    resolver.request('offline')
                self.assertIn('streams', resolver.request('third'))
                self.assertEqual(sock.stat().st_mode & 0o777, 0o600)
                with self.assertRaises(ValueError):
                    resolver.request('../bad')
            finally:
                process.terminate()
                process.join(timeout=5)
