import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from stream_preview_frames import pump_frames


class PreviewFrameTests(unittest.TestCase):
    def test_reuses_connection_and_does_not_queue_stale_frames(self):
        preview = SimpleNamespace(process=SimpleNamespace(pid=123), endpoint='preview.sock',
                                  cancelled=threading.Event())
        submitted = threading.Event()
        pending = []
        player = Mock()
        with tempfile.TemporaryDirectory() as directory, patch('stream_preview_frames.Player', return_value=player) as connect:
            path = Path(directory) / 'frame.jpg'
            path.touch()
            def submit(texture, done):
                pending.append(done)
                submitted.set()
            thread = threading.Thread(target=pump_frames,
                args=(preview, path, lambda _: 'texture', submit, lambda: True))
            thread.start()
            try:
                self.assertTrue(submitted.wait(1))
                # Until GTK consumes the frame there must be no next capture.
                self.assertFalse(preview.cancelled.wait(.08))
                self.assertEqual(len(pending), 1)
                self.assertEqual(player.command.call_count, 2)
                submitted.clear()
                pending[0]()
                self.assertTrue(submitted.wait(1))
                self.assertEqual(len(pending), 2)
                connect.assert_called_once_with('preview.sock', 123)
                self.assertEqual(player.command.call_count, 3)
            finally:
                # Cancellation must work even if GTK never consumes frame two.
                preview.cancelled.set()
                thread.join(1)
            self.assertFalse(thread.is_alive())
            player.close.assert_called_once()
            self.assertFalse(path.exists())

    def test_broken_connection_is_replaced_and_closed(self):
        preview = SimpleNamespace(process=SimpleNamespace(pid=123), endpoint='preview.sock',
                                  cancelled=threading.Event())
        broken, healthy = Mock(), Mock()
        broken.command.side_effect = OSError('disconnected')
        def submit(texture, done):
            preview.cancelled.set()
            done()
        with tempfile.TemporaryDirectory() as directory, patch('stream_preview_frames.Player', side_effect=[broken, healthy]):
            pump_frames(preview, Path(directory)/'frame.jpg', lambda _: 'texture', submit, lambda: True)
        broken.close.assert_called_once()
        healthy.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
