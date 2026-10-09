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
            messages=root/'messages'
            script.write_text('local original_osd=mp.osd_message\nmp.osd_message=function(text,duration) local f=io.open('+json.dumps(str(messages))+',"a");f:write(text .. "\\n");f:close();original_osd(text,duration) end\n'+script.read_text())
            (root/'newsboat-playback-started.py').write_text('pass\n')
            (root/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            (root/'newsboat-playback-target.py').write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'p=Path(__file__).parent\n'
                '(p/"calls").write_text(json.dumps(sys.argv[1:3]))\n'
                'plan=json.loads((p/"plan.json").read_text());plan["episode"]={"number":int(sys.argv[1][-1])+1,"total":3} if plan.get("playlist") else None\n'
                'if plan.get("queue"):\n'
                ' token="token"+sys.argv[1][-1];plan["current_queue_token"]=token;plan["queue_position"]={"number":plan["queue_tokens"].index(token)+1,"total":len(plan["queue_tokens"]),"token":token}\n'
                'print(json.dumps({"url":sys.argv[1],"path":str(p/"next.wav"),"title":sys.argv[2],"local":True,"plan":plan}))\n')
            rows = [dict(url=f'https://www.youtube.com/watch?v=episode000{i}', title=f'Episode {i}') for i in range(3)]
            manifest = root/'playlist.json'
            manifest.write_text(json.dumps(dict(rows=rows)))
            plan = dict(enabled=True, playlist=context, episode=dict(number=index+1,total=3) if context else None,
                        next=rows[index+1] if context and index<2 else None,
                        previous=rows[index-1] if context and index>0 else None)
            if action == 'queue_eof':
                plan['queue']=True
                plan['queue_next']=plan['next']
                plan.update(current_queue_token='token'+str(index),queue_tokens=['token0','token1','token2'],
                            queue_position=dict(number=index+1,total=3,token='token'+str(index)),
                            next_queue_position=dict(number=index+2,total=3,token='token'+str(index+1)))
                (root/'queue.tsv').write_text('initial')
                (root/'newsboat_queue.py').write_text('import json,sys\nfrom pathlib import Path\np=Path(__file__).parent\nif sys.argv[1]=="finished":\n data=json.loads((p/"plan.json").read_text());data["queue_tokens"].remove(sys.argv[3]);data["queue_position"]=None;data["next_queue_position"]["number"]-=1;data["next_queue_position"]["total"]-=1;(p/"plan.json").write_text(json.dumps(data));(p/"queue.tsv").write_text("updated")\n')
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
            env = dict(os.environ, NEWSBOAT_MEDIA_URL=rows[index]['url'],NEWSBOAT_QUEUE_STATUS=str(root/'queue.tsv'))
            env.pop('NEWSBOAT_PLAYLIST_CONTEXT', None)
            if context:
                env['NEWSBOAT_PLAYLIST_CONTEXT'] = str(manifest)
            driver=root/'driver.lua'
            command_file=root/'command'
            loaded=root/'loaded'
            playing=root/'playing'
            title_file=root/'title'
            driver.write_text(
                'local utils=require("mp.utils")\n'
                'mp.observe_property("media-title","string",function(_,title) local f=io.open('+json.dumps(str(title_file))+',"w");f:write(title or "");f:close() end)\n'
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
                label='Queue video' if action=='queue_eof' else 'Episode'
                if context:
                    deadline=time.monotonic()+2
                    while (not title_file.exists() or f'{label} {index+1} of 3' not in title_file.read_text()) and time.monotonic()<deadline:time.sleep(.02)
                    self.assertIn(f'{label} {index+1} of 3',title_file.read_text())
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
                    if context:
                        deadline=time.monotonic()+2
                        while f'{label} {expected+1} of 3' not in title_file.read_text() and time.monotonic()<deadline:time.sleep(.02)
                        self.assertEqual(title_file.read_text(),f'{label} {expected+1} of 3 · '+rows[expected]['title'])
                    if action=='queue_eof':
                        text=messages.read_text()
                        self.assertIn('Watching: Queue video 2 of 3',text)
                        self.assertIn('Queue video 3 of 3 · Episode 2',text)
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
