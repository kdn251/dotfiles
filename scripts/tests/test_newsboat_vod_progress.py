import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import newsboat_vod_progress as progress


class ProgressTests(unittest.TestCase):
    def test_real_transport_stream_duration_percentage_and_byte_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sample.mp4'
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=black:s=32x32:r=25:d=2',
                            '-c:v','mpeg2video','-f','mpegts',str(path)],check=True)
            seconds=progress.downloaded_seconds(path)
            self.assertGreater(seconds,1.8);self.assertLess(seconds,2.1)
            row=dict(path=str(path),url='https://www.twitch.tv/videos/123456789')
            self.assertRegex(progress.label(row,4),r'↓ 4[5-9]%')
            self.assertTrue(progress.label(row).endswith('MB'))
            self.assertEqual(progress.label(row,1),'↓ 99%')

    def test_missing_duration_and_failed_download_stay_honest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);path=root/'partial.mp4';path.write_bytes(b'partial');Path(str(path)+'.incomplete').touch()
            row=dict(id='123',url='https://www.twitch.tv/videos/123',path=str(path))
            with patch.object(progress,'STATE',root),patch.object(progress,'active_rows',side_effect=[[row],[]]),patch.object(progress,'get_duration',return_value=None),patch.object(progress.time,'sleep'):
                progress.monitor()
                self.assertIn('\t✕\n',(root/'download-status.tsv.vods').read_text())

    def test_duration_metadata_is_cached(self):
        with tempfile.TemporaryDirectory() as directory:
            row=dict(id='123',url='https://www.twitch.tv/videos/123')
            with patch.object(progress,'STATE',Path(directory)),patch.object(progress.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'1000\n','')) as run:
                self.assertEqual(progress.get_duration(row),1000)
                self.assertEqual(progress.get_duration(row),1000)
                self.assertEqual(run.call_count,1)

    def test_count_includes_active_deduplicates_and_excludes_partials(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);done=root/'done.mp4';done.touch();partial=root/'partial.mp4';partial.touch();Path(str(partial)+'.incomplete').touch()
            rows=[dict(url='done',path=str(done)),dict(url='active',path=str(partial)),dict(url='deleted',path=str(root/'missing.mp4'))]
            (root/'vod-items.json').write_text(json.dumps(rows))
            with patch.object(progress,'STATE',root):
                self.assertEqual(progress.publish_count([dict(url='active'),dict(url='done')]),2)
                self.assertEqual((root/'starred-urls.txt.vods.count').read_text(),'2\n')
                Path(str(partial)+'.incomplete').unlink()
                self.assertEqual(progress.publish_count([]),2)
                done.unlink()
                self.assertEqual(progress.publish_count([]),1)
                (root/'vod-items.json').unlink()
                self.assertEqual(progress.publish_count([dict(url='active')]),1)
