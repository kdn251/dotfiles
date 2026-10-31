import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import stream_vods as vods

class VodTests(unittest.TestCase):
    def test_local_vods_only_newest_first_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            first=root/'twitch-vods'/'Creator - First title - 1234567890.mp4'
            second=root/'twitch-vods'/'manual'/'Creator - Other title - 1234567891.mp4'
            for path in (first,second):
                path.parent.mkdir(parents=True,exist_ok=True);path.touch()
            with patch.object(vods.media,'ROOT',root),patch.object(vods.media,'records',return_value=[]), \
                    patch.object(vods.media,'candidates',return_value=[(('twitch','1234567890'),first),
                        (('twitch','1234567891'),second),(('twitch','1234567890'),first),
                        (('youtube','abcdefghijk'),first)]),patch.dict(vods.os.environ,{'XDG_STATE_HOME':directory}):
                rows=vods.entries()
                self.assertEqual(len(rows),2)
                self.assertEqual(rows[0]['source'],'Creator')
                self.assertEqual({r['title'] for r in rows},{'First title','Other title'})
                self.assertGreaterEqual(rows[0]['saved'],rows[1]['saved'])

    def test_missing_file_cannot_start_remote_playback(self):
        with patch.object(vods.subprocess,'Popen') as spawn:
            with self.assertRaises(ValueError):vods.play(dict(path='/nonexistent/vod.mp4'))
            spawn.assert_not_called()

    def test_selection_uses_existing_newsboat_playback(self):
        with tempfile.NamedTemporaryFile() as video,patch.object(vods.subprocess,'Popen') as spawn:
            vods.play(dict(path=video.name,url='https://www.twitch.tv/videos/1234567890',title='A VOD'))
            args=spawn.call_args.args[0]
            self.assertTrue(args[1].endswith('/newsboat-play-video.py'))
            self.assertEqual(args[2:],['https://www.twitch.tv/videos/1234567890','A VOD'])
