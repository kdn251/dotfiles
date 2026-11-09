import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('vod_prepare', SCRIPTS/'twitch-vod-prepare.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
import newsboat_media as media


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root/'creator - test - 1234567890.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10',
            '-f','lavfi','-i','sine=frequency=440','-t','2','-c:v','libx264','-c:a','aac',
            '-output_ts_offset','64','-movflags','frag_keyframe+empty_moov',str(self.path)],check=True)
        self.state = patch.object(media, 'STATE', self.root/'state')
        self.state.start()
        self.env = patch.dict(os.environ, {'XDG_STATE_HOME': str(self.root/'runtime-state')})
        self.env.start()

    def tearDown(self):
        self.state.stop()
        self.env.stop()
        self.tmp.cleanup()

    def test_roundtrip_and_idempotence(self):
        original = self.path.stat()
        self.assertTrue(m.fragmented(self.path))
        self.assertTrue(m.prepare(self.path))
        self.assertFalse(m.fragmented(self.path))
        self.assertEqual(original.st_mtime_ns, self.path.stat().st_mtime_ns)
        self.assertFalse(m.prepare(self.path))

    def test_low_space_and_playing_preserve_original(self):
        before = self.path.read_bytes()
        with patch.object(m, 'playing', return_value=True):
            with self.assertRaises(RuntimeError):m.prepare(self.path)
        with patch.object(m.shutil, 'disk_usage') as usage:
            usage.return_value.free = 0
            with self.assertRaises(RuntimeError):m.prepare(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_failed_remux_preserves_original(self):
        before = self.path.read_bytes()
        probe = m.probe(self.path)
        with patch.object(m, 'probe', return_value=probe), patch.object(m, 'remux',
                side_effect=subprocess.CalledProcessError(1, 'ffmpeg')):
            with self.assertRaises(subprocess.CalledProcessError):m.prepare(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(self.path.with_name('.'+self.path.name+'.preparing.mp4').exists())

    def test_transport_stream_unchanged(self):
        self.path.write_bytes(b'\x47'+b'\x00'*375)
        self.assertFalse(m.fragmented(self.path))
        self.assertFalse(m.prepare(self.path))

    def test_stale_output_is_replaced_on_retry(self):
        temp = self.path.with_name('.'+self.path.name+'.preparing.mp4')
        temp.write_bytes(b'interrupted output')
        self.assertTrue(m.prepare(self.path))
        self.assertFalse(temp.exists())

    def test_validation_failure_preserves_original(self):
        before = self.path.read_bytes()
        valid = m.probe(self.path)
        with patch.object(m, 'probe', side_effect=[valid, (valid[0], 500)]):
            with self.assertRaises(ValueError):m.prepare(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_preparation_label(self):
        import newsboat_vod_progress as progress
        self.assertEqual(progress.label({'preparing': True}), 'Preparing')

    def test_downloader_retries_preparation_before_live_check(self):
        home=self.root/'home'
        vods=home/'Videos/newsboat/twitch-vods';vods.mkdir(parents=True)
        scripts=home/'scripts';scripts.mkdir()
        avatar=scripts/'twitch-profile-pic.sh';avatar.write_text('#!/bin/sh\nexit 0\n');avatar.chmod(0o755)
        old=vods/'creator - old - 1111111111.mp4';old.write_bytes(b'old')
        new=vods/'creator - new - 2222222222.mp4';new.write_bytes(b'new')
        marker=Path(str(new)+'.download-complete');marker.touch()
        incomplete=Path(str(new)+'.incomplete');incomplete.touch()
        archive=vods.parent/'.downloaded-twitch-vods';archive.write_text('creator:1111111111\n')
        source=(SCRIPTS/'twitch-vod-downloader.sh').read_text().split('# MAIN EXECUTION LOOP')[0]
        # Stub external services. A live streamer must still finish a pending
        # preparation without invoking Streamlink or yt-dlp again.
        fixture=source+'''
notify-send() { :; }
write_status() { :; }
sleep() { :; }
is_streamer_live() { return 0; }
python3() { return "$PREPARE_RESULT"; }
download_vods creator
'''
        env=dict(os.environ,HOME=str(home),PREPARE_RESULT='1')
        subprocess.run(['bash','-c',fixture],env=env,capture_output=True)
        self.assertTrue(old.exists());self.assertTrue(marker.exists());self.assertTrue(incomplete.exists())
        self.assertEqual(archive.read_text(),'creator:1111111111\n')
        env['PREPARE_RESULT']='0'
        subprocess.run(['bash','-c',fixture],env=env,capture_output=True,check=True)
        self.assertFalse(old.exists());self.assertFalse(marker.exists());self.assertFalse(incomplete.exists())
        self.assertEqual(new.read_bytes(),b'new')
        self.assertEqual(archive.read_text(),'creator:2222222222\n')


if __name__ == '__main__':unittest.main()
