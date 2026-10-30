import importlib.util
from pathlib import Path
import unittest
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location('notice', Path(__file__).resolve().parents[1]/'scripts/stream-loading-notification.py')
notice = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notice)

class LoadingNotificationTests(unittest.TestCase):
    def test_waits_for_selected_stream_not_previous_playback(self):
        connection = MagicMock()
        with patch.object(notice.Path, 'read_text', return_value='new'), \
                patch.object(notice.ipc, 'connect', return_value=(connection, 1)), \
                patch.object(notice.ipc, 'command', side_effect=['old', 'new']), \
                patch.object(notice.time, 'sleep') as sleep, \
                patch.object(notice.subprocess, 'run') as run:
            notice.watch('new', '123')
            sleep.assert_called_once()
            self.assertEqual(run.call_args.args[0][-2:], ['org.freedesktop.Notifications.CloseNotification','123'])
            self.assertEqual(run.call_args.args[0][0], 'gdbus')

    def test_replaced_selection_dismisses_only_its_own_notice(self):
        with patch.object(notice.Path, 'read_text', return_value='newer'), \
                patch.object(notice.ipc, 'connect') as connect, \
                patch.object(notice.subprocess, 'run') as run:
            notice.watch('old', '456')
            connect.assert_not_called()
            self.assertEqual(run.call_args.args[0][-1], '456')
