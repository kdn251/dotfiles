"""Exercise playlist navigation in real mpv without opening network media."""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import wave

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'


@unittest.skipUnless(shutil.which('mpv'), 'requires mpv')
class PlaylistPlaybackTests(unittest.TestCase):
    def run_player(self, action, index=1, expected=None, context=True):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, ipc, calls = root/'video.wav', root/'ipc', root/'calls'
            with wave.open(str(source), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b'\0' * 8000)
            script = root/'newsboat-playlist-playback.lua'
            shutil.copyfile(SCRIPTS/script.name, script)
            (root/'newsboat-play-video.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'Path(__file__).with_name("calls").write_text(json.dumps(sys.argv[1:]))\n')
            rows = [dict(url=f'https://www.youtube.com/watch?v=episode000{i}', title=f'Episode {i}') for i in range(3)]
            manifest = root/'playlist.json'
            manifest.write_text(json.dumps(dict(rows=rows)))
            env = dict(os.environ, NEWSBOAT_MEDIA_URL=rows[index]['url'])
            env.pop('NEWSBOAT_PLAYLIST_CONTEXT', None)
            if context:
                env['NEWSBOAT_PLAYLIST_CONTEXT'] = str(manifest)
            process = subprocess.Popen(['mpv', '--no-config', '--vo=null', '--ao=null', '--pause', '--idle=no' if action == 'eof' else '--idle=yes',
                '--log-file='+str(root/'mpv.log'), '--input-ipc-server='+str(ipc), '--script='+str(script), str(source)], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+5
                while not ipc.exists() and time.monotonic()<deadline:
                    time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as connection:
                    connection.settimeout(3)
                    connection.connect(str(ipc))
                    with connection.makefile('rwb', buffering=0) as stream:
                        def command(args):
                            stream.write((json.dumps(dict(command=args, request_id=1))+'\n').encode())
                            while True:
                                response=json.loads(stream.readline())
                                if response.get('request_id')==1:
                                    return response
                        deadline = time.monotonic()+3
                        while command(['get_property', 'duration']).get('data', 0)==0 and time.monotonic()<deadline:
                            time.sleep(.02)
                        if action == 'eof':
                            command(['set_property', 'pause', False])
                        elif action == 'replace':
                            command(['loadfile', str(source), 'replace'])
                        elif action == 'stop':
                            command(['stop'])
                        else:
                            command(['keypress', action])
                        deadline = time.monotonic()+(3 if expected is not None else .7)
                        while not calls.exists() and time.monotonic()<deadline:
                            time.sleep(.02)
                        if expected is None:
                            self.assertFalse(calls.exists())
                        else:
                            self.assertTrue(calls.exists(), (root/'mpv.log').read_text()[-5000:])
                            self.assertEqual(json.loads(calls.read_text()), [rows[expected]['url'], rows[expected]['title']])
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_next_and_previous(self):
        self.run_player('>', expected=2)
        self.run_player('<', expected=0)

    def test_natural_end_advances(self):
        self.run_player('eof', expected=2)

    def test_boundaries_do_not_wrap(self):
        self.run_player('<', index=0)
        self.run_player('>', index=2)
        self.run_player('eof', index=2)

    def test_stop_and_local_handoff_do_not_advance(self):
        self.run_player('stop')
        self.run_player('replace')

    def test_outside_playlist_does_not_autoplay(self):
        self.run_player('eof', context=False)
