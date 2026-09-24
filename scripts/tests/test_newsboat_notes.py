import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('notes', SCRIPTS/'newsboat-notes.py')
notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notes)


class NotesTests(unittest.TestCase):
    def test_edit_reopen_clear_and_separate_items(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            env = {'XDG_DATA_HOME':str(root/'data'), 'NEWSBOAT_NOTES_STATUS':str(root/'notes.tsv'), 'VISUAL':'fake-editor --example'}
            url = 'https://example.com/article?a=1&b=2'
            paths = []
            def write(args):
                self.assertEqual(args[:2], ['fake-editor','--example'])
                path=Path(args[-1]);paths.append(path)
                path.write_text('My commentary idea\n')
                return 0
            with patch.dict(os.environ,env), patch.object(notes.subprocess,'call',side_effect=write):
                notes.edit(url)
                self.assertEqual(notes.status_path().read_text(), url+'\n')
                notes.edit(url)
                self.assertEqual(paths[0],paths[1])
                notes.edit('https://example.com/another')
                self.assertNotEqual(paths[0],paths[2])
                paths[0].write_text(' \n\t')
                notes.publish()
                self.assertEqual(notes.status_path().read_text(),'https://example.com/another\n')
                self.assertTrue(paths[0].exists())

    def test_empty_editor_visit_does_not_add_badge(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with patch.dict(os.environ, XDG_DATA_HOME=str(root/'data'),NEWSBOAT_NOTES_STATUS=str(root/'status')), patch.object(notes.subprocess,'call',return_value=0):
                notes.edit('https://example.com/empty')
                self.assertEqual(notes.status_path().read_text(),'')
