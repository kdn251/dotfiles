import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('restore',Path(__file__).resolve().parents[1]/'scripts/restore-pip-position.py')
restore=importlib.util.module_from_spec(spec);spec.loader.exec_module(restore)

class RestoreTests(unittest.TestCase):
    def test_direct_restore_does_not_trigger_delayed_move(self):
        w=dict(address='0x123',pid=123,mapped=True,floating=True,fullscreen=0,
               at=[100,200],size=[420,240],title='video', **{'class':'mpv'})
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore,'restore') as move:
            tracker=restore.Tracker(tmp)
            tracker.update([w])
            tracker.update([dict(w,fullscreen=2)])
            marker=Path(tmp)/f'pip-fullscreen-{os.getuid()}-0x123.geometry.restored'
            marker.write_text('123')
            tracker.update([w])
            move.assert_not_called()
            self.assertFalse(marker.exists())
            tracker.update([dict(w,fullscreen=2)])
            tracker.update([w])
            move.assert_called_once_with('0x123',(100,200,420,240))

if __name__=='__main__':unittest.main()
