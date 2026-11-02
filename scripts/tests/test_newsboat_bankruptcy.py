import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('bankruptcy',Path(__file__).parents[1]/'scripts/newsboat-bankruptcy.py')
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class BankruptcyTests(unittest.TestCase):
    def test_preserves_playlist_files_metadata_and_vods_clears_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);library=root/'videos';state=root/'state/newsboat'
            downloads=state/'downloads';downloads.mkdir(parents=True)
            groups=downloads.parent/'youtube-playlists/playthroughs';groups.mkdir(parents=True)
            ordinary=library/'ordinary [aaaaaaaaaaa].mp4'
            member=library/'shared [bbbbbbbbbbb].mp4'
            vod=library/'twitch-vods'/'Creator - VOD - 1234567890.mp4'
            for p in (ordinary,member,vod):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'video')
            group=groups/'example.json'
            group.write_text(json.dumps(dict(rows=[dict(url='https://youtu.be/bbbbbbbbbbb')],selected_urls=[])))
            original=group.read_bytes()
            (state/'viewing-queue.json').write_text(json.dumps([dict(url='https://youtu.be/aaaaaaaaaaa',queue_token='x')]))
            (state/'queue-navigation.json').write_text('[{"url":"old"}]')
            (state/'queue-current.json').write_text('{"url":"old"}')
            with patch.dict(os.environ,{'XDG_STATE_HOME':str(root/'state')}), \
                    patch.object(b.media,'ROOT',library),patch.object(b.media,'CACHE',root/'cache'), \
                    patch.object(b.media,'STATE',downloads),patch.object(b.media,'rebuild'),patch.object(b.queue,'publish'):
                removed,errors=b.execute()
                self.assertEqual(removed,1);self.assertEqual(errors,[])
                self.assertFalse(ordinary.exists());self.assertEqual(member.read_bytes(),b'video')
                self.assertEqual(vod.read_bytes(),b'video');self.assertEqual(group.read_bytes(),original)
                self.assertEqual(b.queue.entries(),[])
                self.assertEqual(json.loads((state/'queue-navigation.json').read_text()),[])
                self.assertFalse((state/'queue-current.json').exists())

    def test_bad_playlist_metadata_aborts_before_any_change(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'bad.json').write_text('{broken')
            with patch.object(b.playlists,'directory',return_value=root),patch.object(b.media,'delete') as delete:
                with self.assertRaises(ValueError):b.targets()
                delete.assert_not_called()

    def test_requires_confirmation_flag(self):
        with patch.object(b.sys,'argv',['newsboat-bankruptcy.py']),patch.object(b,'execute') as execute:
            self.assertEqual(b.main(),2);execute.assert_not_called()

    def test_delete_rechecks_protection_under_lock(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(b.media,'STATE',Path(directory)), \
                patch.object(b.media,'candidates') as candidates:
            self.assertEqual(b.media.delete('https://youtu.be/aaaaaaaaaaa',protect=lambda key:True),0)
            candidates.assert_not_called()
