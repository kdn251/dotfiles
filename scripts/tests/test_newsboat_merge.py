"""Real stream-copy merge, lock exclusion, and disk pacing checks."""
import fcntl
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

WRAPPER=Path(__file__).resolve().parents[1]/'scripts/newsboat-ffmpeg/ffmpeg'
loader=importlib.machinery.SourceFileLoader('merge_wrapper',str(WRAPPER))
spec=importlib.util.spec_from_loader(loader.name,loader)
merge=importlib.util.module_from_spec(spec);loader.exec_module(merge)

class MergeTests(unittest.TestCase):
    def test_pacing_uses_combined_input_size_without_changing_codecs(self):
        with tempfile.TemporaryDirectory() as d:
            files=[Path(d)/name for name in ('video','audio')]
            for p in files:
                with p.open('wb') as f:f.truncate(32*1024*1024)
            args=['-i',str(files[0]),'-i',str(files[1]),'-c','copy','out.mp4']
            with patch.object(merge.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'2\n')):
                result=merge.paced_arguments(args)
            self.assertEqual(result.count('-readrate'),2)
            self.assertEqual([result[i+1] for i,v in enumerate(result) if v=='-readrate'],['1.000000','1.000000'])
            self.assertEqual(result[-3:],['-c','copy','out.mp4'])

    def test_real_merge_waits_for_slot_and_preserves_streams(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.mp4';output=root/'merged.mp4'
            subprocess.run(['/usr/bin/ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=160x90:r=10',
                            '-f','lavfi','-i','sine=frequency=400','-t','1','-c:v','libx264','-threads','1','-c:a','aac',str(source)],check=True)
            state=root/'newsboat/downloads';state.mkdir(parents=True)
            with (state/'.merge.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                process=subprocess.Popen([str(WRAPPER),'-v','error','-i',str(source),'-c','copy','-movflags','-faststart',str(output)],
                                         env=dict(os.environ,XDG_STATE_HOME=d),stderr=subprocess.PIPE)
                try:
                    time.sleep(.2)
                    self.assertIsNone(process.poll());self.assertFalse(output.exists())
                    fcntl.flock(lock,fcntl.LOCK_UN)
                    _,error=process.communicate(timeout=10)
                    self.assertEqual(process.returncode,0,error.decode())
                finally:
                    if process.poll() is None:process.kill();process.wait()
            def streams(path):
                return json.loads(subprocess.check_output(['/usr/bin/ffprobe','-v','error','-show_entries','stream=codec_name,codec_type,duration','-of','json',str(path)]))['streams']
            self.assertEqual(streams(source),streams(output))

    def test_network_inputs_are_not_paced(self):
        args=['-i','https://example.com/live','-c','copy','out.mp4']
        self.assertEqual(merge.paced_arguments(args),args)
