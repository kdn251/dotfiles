"""Exercise playlist navigation in real mpv without opening network media."""
import json
import os
from pathlib import Path
import shutil
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
            source, calls = root/'video.wav', root/'calls'
            with wave.open(str(source), 'wb') as out:
                out.setnchannels(1)
                out.setsampwidth(2)
                out.setframerate(8000)
                out.writeframes(b'\0' * 8000)
            with wave.open(str(root/'next.wav'), 'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*160000)
            script = root/'newsboat-playlist-playback.lua'
            shutil.copyfile(SCRIPTS/script.name, script)
            (root/'newsboat-playback-started.py').write_text('pass\n')
            (root/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            (root/'newsboat-playback-target.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'p=Path(__file__).parent\n'
                '(p/"calls").write_text(json.dumps(sys.argv[1:3]))\n'
                'print(json.dumps({"url":sys.argv[1],"path":str(p/"next.wav"),"title":sys.argv[2],"local":True,"plan":json.loads((p/"plan.json").read_text())}))\n')
            rows = [dict(url=f'https://www.youtube.com/watch?v=episode000{i}', title=f'Episode {i}') for i in range(3)]
            manifest = root/'playlist.json'
            manifest.write_text(json.dumps(dict(rows=rows)))
            plan = dict(enabled=True, playlist=context,
                        next=rows[index+1] if context and index<2 else None,
                        previous=rows[index-1] if context and index>0 else None)
            if action == 'queue_eof':
                plan['queue']=True
                plan['queue_next']=plan['next']
            if action == 'random':
                plan['next'] = rows[2]
            (root/'plan.json').write_text(json.dumps(plan))
            (root/'newsboat_autoplay.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'p=Path(__file__).with_name("plan.json")\n'
                'data=json.loads(p.read_text())\n'
                'if sys.argv[1]=="set":\n'
                ' data["enabled"]=sys.argv[2]=="on";p.write_text(json.dumps(data))\n'
                'else: print(json.dumps(data))\n')
            env = dict(os.environ, NEWSBOAT_MEDIA_URL=rows[index]['url'])
            env.pop('NEWSBOAT_PLAYLIST_CONTEXT', None)
            if context:
                env['NEWSBOAT_PLAYLIST_CONTEXT'] = str(manifest)
            driver=root/'driver.lua'
            command_file=root/'command'
            loaded=root/'loaded'
            playing=root/'playing'
            driver.write_text(
                'local utils=require("mp.utils")\n'
                'mp.observe_property("time-pos","number",function(_,position) if mp.get_property("path")=='+json.dumps(str(root/'next.wav'))+' and position and position>.15 and not mp.get_property_native("pause") then local f=io.open('+json.dumps(str(playing))+',"w");f:write("playing");f:close() end end)\n'
                'mp.register_event("file-loaded",function() local f=io.open('+json.dumps(str(loaded))+',"a");f:write("loaded\\n");f:close() end)\n'
                'mp.add_periodic_timer(.02,function() local f=io.open('+json.dumps(str(command_file))+',"r");if f then local cmd=utils.parse_json(f:read("*a"));f:close();os.remove('+json.dumps(str(command_file))+');if cmd[1]=="set_property" then mp.set_property_native(cmd[2],cmd[3]) else mp.command_native(cmd) end end end)\n')
            process = subprocess.Popen(['mpv', '--no-config', '--vo=null', '--ao=null', '--pause', '--keep-open=yes', '--idle=yes',
                '--log-file='+str(root/'mpv.log'), '--script='+str(driver), '--script='+str(script), str(source)], env=env,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                def command(args):
                    tmp=root/'pending';tmp.write_text(json.dumps(args));tmp.replace(command_file)
                    deadline=time.monotonic()+3
                    while command_file.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertFalse(command_file.exists())
                deadline=time.monotonic()+5
                while not loaded.exists() and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(loaded.exists())
                if action in ('eof', 'queue_eof', 'random', 'cancel', 'off'):
                    if action == 'off':command(['keypress','A'])
                    command(['set_property','pause',False])
                    time.sleep(1)
                    self.assertFalse(calls.exists(), 'Must display countdown before loading')
                    if action == 'cancel':command(['keypress','A'])
                elif action == 'replace':command(['loadfile',str(source),'replace'])
                elif action == 'stop':command(['stop'])
                else:command(['keypress',action])
                deadline=time.monotonic()+(6 if expected is not None or action in ('off','cancel') else .7)
                while not calls.exists() and time.monotonic()<deadline:time.sleep(.02)
                if expected is None:self.assertFalse(calls.exists())
                else:
                    self.assertTrue(calls.exists(),(root/'mpv.log').read_text()[-5000:])
                    self.assertEqual(json.loads(calls.read_text()),[rows[expected]['url'],rows[expected]['title']])
                    deadline=time.monotonic()+3
                    while len(loaded.read_text().splitlines())<2 and time.monotonic()<deadline:time.sleep(.02)
                    self.assertGreaterEqual(len(loaded.read_text().splitlines()),2,'replacement loaded inside the same player')
                    self.assertIsNone(process.poll(),'player survives the transition')
                    if action in ('eof','queue_eof','random'):
                        deadline=time.monotonic()+3
                        while not playing.exists() and time.monotonic()<deadline:time.sleep(.02)
                        self.assertTrue(playing.exists(),'autoplay replacement must advance playback without a manual unpause')
            finally:
                process.terminate()
                process.wait(timeout=5)

    def test_next_and_previous(self):
        self.run_player('>', expected=2)
        self.run_player('<', expected=0)

    def test_natural_end_advances(self):
        self.run_player('eof', expected=2)

    def test_queue_natural_end_starts_next_video_unpaused(self):
        self.run_player('queue_eof', expected=2)

    def test_boundaries_do_not_wrap(self):
        self.run_player('<', index=0)
        self.run_player('>', index=2)
        self.run_player('eof', index=2)

    def test_stop_and_local_handoff_do_not_advance(self):
        self.run_player('stop')
        self.run_player('replace')

    def test_outside_playlist_does_not_autoplay(self):
        self.run_player('eof', context=False)

    def test_autoplay_off_and_cancel_countdown(self):
        self.run_player('off')
        self.run_player('cancel')

    def test_random_download_autoplay(self):
        self.run_player('random', context=False, expected=2)
