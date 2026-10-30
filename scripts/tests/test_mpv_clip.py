import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from mpv_clip import Player, clip_range, save

ROOT=Path(__file__).resolve().parents[2]

class ClipTests(unittest.TestCase):
    def test_uses_current_range_not_first_range(self):
        self.assertEqual(clip_range(120,30,[{'start':0,'end':20},{'start':110,'end':130}]),(110,120))
        self.assertEqual(clip_range(120,30,[{'start':90,'end':110},{'start':105,'end':130}]),(90,120))
        with self.assertRaises(ValueError):clip_range(50,30,[{'start':0,'end':20}])
        with self.assertRaises(ValueError):clip_range(1,30,[{'start':0,'end':8}])

    def test_actual_hotkey_and_split_youtube_audio_video(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=160x90:rate=10',
                            '-f','lavfi','-i','sine=frequency=440','-t','8','-c:v','libx264','-preset','ultrafast',
                            '-g','10','-c:a','aac',str(root/'muxed.mp4')],check=True)
            subprocess.run(['ffmpeg','-v','error','-i',str(root/'muxed.mp4'),'-an','-c:v','libvpx-vp9','-deadline','realtime','-cpu-used','8',str(root/'video.webm')],check=True)
            subprocess.run(['ffmpeg','-v','error','-i',str(root/'muxed.mp4'),'-vn','-c:a','libopus',str(root/'audio.webm')],check=True)
            binding=next(line for line in (ROOT/'mpv/.config/mpv/input.conf').read_text().splitlines() if line.startswith('C '))
            (root/'input.conf').write_text(binding+'\n')
            # Keep regression tests from displaying desktop notifications.
            (root/'notify-send').write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$CLIP_TEST_NOTICE"\n')
            (root/'notify-send').chmod(0o700)
            sources=[str(root/'muxed.mp4'),'edl://!new_stream;'+str(root/'video.webm')+';!new_stream;'+str(root/'audio.webm')]
            for index,source in enumerate(sources):
                endpoint=str(root/f'ipc{index}')
                output=root/f'clips{index}';notice=root/f'notice{index}'
                process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--cache=yes',
                                          '--demuxer-max-back-bytes=20MiB','--input-ipc-server='+endpoint,
                                          '--input-conf='+str(root/'input.conf'),source],
                                         env=dict(os.environ,PATH=str(root)+':'+os.environ['PATH'],CLIP_DIR=str(output),CLIP_TEST_NOTICE=str(notice)),
                                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                player=None
                try:
                    deadline=time.monotonic()+7
                    while time.monotonic()<deadline:
                        try:
                            if player is None:player=Player(endpoint,process.pid)
                            if (player.get('time-pos',0) or 0)>3:break
                        except (OSError,ValueError):pass
                        time.sleep(.05)
                    player.command('keypress','C')
                    deadline=time.monotonic()+5
                    while not notice.exists() and time.monotonic()<deadline:time.sleep(.05)
                    self.assertTrue(notice.exists())
                    self.assertIn('Saved',notice.read_text())
                    clips=list(output.iterdir())
                    self.assertEqual(len(clips),1)
                    self.assertEqual(clips[0].suffix,'.mp4' if index==0 else '.mkv')
                    import json
                    streams=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','stream=codec_type','-of','json',str(clips[0])]))['streams']
                    self.assertEqual({s['codec_type'] for s in streams},{'video','audio'})
                finally:
                    if player:player.close()
                    process.terminate();process.wait(timeout=5)
