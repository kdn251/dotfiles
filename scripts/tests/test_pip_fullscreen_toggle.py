import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('toggle', Path(__file__).resolve().parents[1] / 'scripts/toggle-pip-fullscreen.py')
toggle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toggle)


class ToggleTests(unittest.TestCase):
    def test_pinned_roundtrip_uses_one_transaction_and_restores_snapshot(self):
        client = dict(address='0x123', pid=123, floating=True, fullscreen=0,
                      pinned=True, at=[100, 200], size=[420, 240], **{'class': 'mpv'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(toggle.subprocess, 'run') as run:
            root = Path(tmp)
            toggle.toggle(client, root)
            self.assertEqual(run.call_count, 1)
            script = run.call_args.args[0][-1]
            self.assertLess(script.index('window.pin'), script.index('window.fullscreen'))
            run.reset_mock()
            toggle.toggle(dict(client, fullscreen=2, pinned=False, at=[0, 0], size=[1440, 960]), root)
            self.assertEqual(run.call_count, 1)
            script = run.call_args.args[0][-1]
            self.assertLess(script.index('window.fullscreen'), script.index('window.resize'))
            self.assertLess(script.index('window.move'), script.index('window.pin'))
            self.assertIn('["x"]=100', script)
            marker = root / f'pip-fullscreen-{os.getuid()}-0x123.geometry.restored'
            self.assertEqual(toggle.read(marker), 123)
            self.assertFalse(Path(str(marker).replace('.restored', '.return')).exists())

    def test_stale_snapshot_cannot_move_or_pin_reused_address(self):
        client = dict(address='0x123', pid=456, fullscreen=2, pinned=False, **{'class': 'mpv'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(toggle.subprocess, 'run') as run:
            root = Path(tmp)
            prefix = root / f'pip-fullscreen-{os.getuid()}-0x123'
            toggle.write(Path(str(prefix) + '.geometry.return'), dict(pid=123, floating=True))
            toggle.write(Path(str(prefix) + '.pinned'), 123)
            toggle.toggle(client, root)
            script = run.call_args.args[0][-1]
            self.assertNotIn('window.resize', script)
            self.assertNotIn('window.pin', script)

    def test_managed_streams_use_targeted_mpv_fullscreen_not_focused_window(self):
        for service in ('Twitch','YouTube','Kick','Rumble'):
            with self.subTest(service=service),tempfile.TemporaryDirectory() as tmp:
                client=dict(address='0x123',pid=123,floating=True,fullscreen=0,pinned=True,
                            at=[100,200],size=[420,240],**{'class':'mpv'})
                properties={'user-data/stream-service':service,'fullscreen':False}
                def ipc(state,op,key,*args):
                    if op=='get_property':return properties[key]
                    properties[key]=args[0]
                with patch('media_chat_fullscreen.socket_for',return_value='player.sock'), \
                        patch('media_chat_fullscreen.ipc',side_effect=ipc) as command, \
                        patch.object(toggle.subprocess,'run') as native, \
                        patch.object(toggle,'query',return_value=[dict(client,fullscreen=0)]), \
                        patch('stream_sidebar.restore_windowed') as restore:
                    toggle.toggle(client,Path(tmp))
                    self.assertTrue(properties['fullscreen'])
                    toggle.toggle(dict(client,fullscreen=2,pinned=False),Path(tmp))
                    self.assertFalse(properties['fullscreen'])
                    restore.assert_called_once()
                    for call in native.call_args_list:
                        self.assertNotIn('window.fullscreen',call.args[0][-1])
                        self.assertNotIn('hl.dsp.focus',call.args[0][-1])
