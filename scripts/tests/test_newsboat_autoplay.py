import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_autoplay as autoplay
import newsboat_media as media


class AutoplayTests(unittest.TestCase):
    def test_preference_persists(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, XDG_STATE_HOME=folder):
            self.assertTrue(autoplay.enabled())
            media.atomic_write(autoplay.preference(), '{"enabled":false}')
            self.assertFalse(autoplay.enabled())

    def test_playlist_order_and_last_episode_does_not_fall_back_to_random(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest=Path(folder)/'playlist.json'
            rows=[dict(url='https://www.youtube.com/watch?v='+str(i)*11,title=str(i)) for i in range(3)]
            manifest.write_text(json.dumps(dict(rows=rows)))
            with patch.dict(os.environ, NEWSBOAT_PLAYLIST_CONTEXT=str(manifest), XDG_STATE_HOME=folder, NEWSBOAT_QUEUE_PLAYBACK='0'), patch.object(autoplay,'download_candidates') as random:
                plan=autoplay.plan(rows[1]['url'])
                self.assertEqual(plan['episode'],dict(number=2,total=3))
                self.assertIsNone(autoplay.episode_context('https://youtu.be/99999999999'))
                self.assertEqual(autoplay.episode_context('https://youtu.be/11111111111'),dict(number=2,total=3))
                self.assertEqual(plan['next'], rows[2])
                self.assertEqual(plan['previous'], rows[0])
                self.assertIsNone(autoplay.plan(rows[2]['url'])['next'])
                random.assert_not_called()

    def test_download_pool_excludes_current_unfinished_vods_playthroughs_and_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'state';state.mkdir();videos=root/'videos';videos.mkdir()
            paths=[videos/(f'Video [{str(i)*11}].mp4') for i in range(5)]
            for path in paths:path.touch()
            paths[4].unlink()
            vod=videos/'twitch-vods'/'Streamer [v123456789].mp4';vod.parent.mkdir();vod.touch()
            index={str(p):dict(valid=i!=3) for i,p in enumerate(paths)}
            index[str(vod)]=dict(valid=True)
            (state/'.media-index.json').write_text(json.dumps(index))
            with patch.object(media,'STATE',state),patch.object(media,'ROOT',videos),patch.object(media,'cached_title',return_value='Saved title'),patch('newsboat_playthroughs.member_keys',return_value={('youtube','2'*11)}):
                pool=autoplay.download_candidates('https://youtu.be/'+'0'*11)
                self.assertEqual(pool,[dict(url='https://www.youtube.com/watch?v='+'1'*11,title=paths[1].stem)])
