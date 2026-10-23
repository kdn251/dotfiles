"""New additions lead the Queue without overriding manual ordering or undo."""
import os
import unittest
from unittest.mock import patch
from test_newsboat_queue import isolated, URLS
import newsboat_queue as queue

class NewestQueueTests(unittest.TestCase):
    def test_newest_first_dedup_and_resume(self):
        with isolated():
            for url in URLS[:3]:
                queue.change('add', url)
            queue.change('add', 'https://youtu.be/' + '1'*11)
            self.assertEqual([r['url'] for r in queue.entries()], list(reversed(URLS[:3])))
            with patch('newsboat_resume.launch') as launch, patch.dict(os.environ):
                queue.resume()
                self.assertEqual(launch.call_args.args[0]['url'], URLS[2])
            self.assertEqual(queue.navigation(URLS[2])[0]['url'], URLS[1])
            self.assertEqual(queue.navigation(URLS[1])[1]['url'], URLS[2])

    def test_manual_order_survives_add_and_undo(self):
        with isolated():
            for url in URLS[:3]:
                queue.change('add', url)
            queue.change('move-before', URLS[0], URLS[2])
            before = queue.entries()
            with patch.dict(os.environ, NEWSBOAT_QUEUE_UNDO_TOKEN='newest-add'):
                queue.change('add', URLS[3])
            self.assertEqual(queue.entries()[1:], before)
            queue.change('restore', URLS[3], 'newest-add')
            self.assertEqual(queue.entries(), before)
            queue.change('refresh')
            self.assertEqual(queue.entries(), before)

if __name__ == '__main__':
    unittest.main()
