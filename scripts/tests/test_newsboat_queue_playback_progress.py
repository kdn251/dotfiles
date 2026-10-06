"""Real mpv in-place queue navigation preserves each video's progress and EOF."""
from contextlib import closing
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
import wave

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
URLS=['https://www.youtube.com/watch?v='+str(i)*11 for i in (1,2)]

@unittest.skipUnless(shutil.which('mpv'),'requires mpv')
class QueuePlaybackProgressTests(unittest.TestCase):
    def test_progress_follows_queue_navigation_and_records_held_eof(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);scripts=root/'scripts';scripts.mkdir()
            for name in ('newsboat-watch-completion.lua','newsboat-playlist-playback.lua'):
                shutil.copyfile(SCRIPTS/name,scripts/name)
            for i,seconds in enumerate((20,10)):
                with wave.open(str(root/f'{i}.wav'),'wb') as out:
                    out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*16000*seconds)
            (scripts/'newsboat-playback-started.py').write_text('pass\n')
            (scripts/'newsboat_queue.py').write_text('pass\n')
            (scripts/'newsboat-up-next-thumbnail.py').write_text('raise SystemExit(1)\n')
            plans={url:dict(enabled=False,queue=True,current_queue_token=str(i),next=None,
                    queue_next=dict(url=URLS[1],title='Second',queue_token='1') if i==0 else None,
                    previous=dict(url=URLS[0],title='First',queue_token='0') if i else None)
                    for i,url in enumerate(URLS)}
            (root/'plans.json').write_text(json.dumps(plans))
            (scripts/'newsboat_autoplay.py').write_text('import json,sys\nfrom pathlib import Path\nplans=json.loads((Path(__file__).parent.parent/"plans.json").read_text())\nprint(json.dumps(plans[sys.argv[2]]))\n')
            (scripts/'newsboat-playback-target.py').write_text('import json,sys\nfrom pathlib import Path\nr=Path(__file__).parent.parent\np=json.loads((r/"plans.json").read_text())\ni=list(p).index(sys.argv[1])\nprint(json.dumps(dict(url=sys.argv[1],path=str(r/f"{i}.wav"),title=sys.argv[2],plan=p[sys.argv[1]],**{"local":True})))\n')
            command=root/'command';events=root/'events'
            driver=root/'driver.lua'
            driver.write_text('local u=require("mp.utils")\n'
                'mp.register_event("playback-restart",function() local f=io.open('+json.dumps(str(events))+',"a");f:write(u.format_json({path=mp.get_property("path"),position=mp.get_property_number("time-pos")}).."\\n");f:close() end)\n'
                'mp.add_periodic_timer(.02,function() local f=io.open('+json.dumps(str(command))+',"r");if f then local c=u.parse_json(f:read("*a"));f:close();os.remove('+json.dumps(str(command))+');if c[1]=="set" then mp.set_property_native(c[2],c[3]) else mp.command_native(c) end end end)\n')
            env=dict(os.environ,HOME=folder,XDG_STATE_HOME=str(root/'state'),NEWSBOAT_MEDIA_URL=URLS[0],NEWSBOAT_MAINTENANCE=str(SCRIPTS/'newsboat-maintenance.py'),NEWSBOAT_CACHE=str(root/'cache'),NEWSBOAT_QUEUE_STATUS=str(root/'queue'))
            proc=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause','--keep-open=yes','--idle=yes','--script='+str(driver),'--script='+str(scripts/'newsboat-watch-completion.lua'),'--script='+str(scripts/'newsboat-playlist-playback.lua'),str(root/'0.wav')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def wait(test,seconds=8):
                end=time.monotonic()+seconds
                while time.monotonic()<end:
                    if test():return
                    time.sleep(.03)
                self.fail('mpv progress condition timed out: '+repr([progress(0),progress(1),last()]))
            def send(args):
                tmp=root/'pending';tmp.write_text(json.dumps(args));tmp.replace(command)
                wait(lambda:not command.exists(),2)
            def progress(index):
                try:
                    with closing(sqlite3.connect((root/'state/newsboat/watch-progress.db').as_uri()+'?mode=ro',uri=True)) as db:
                        return db.execute('SELECT fraction,position,duration FROM progress WHERE url=?',(URLS[index],)).fetchone()
                except sqlite3.Error:return None
            def last():
                try:return json.loads(events.read_text().splitlines()[-1])
                except (OSError,ValueError,IndexError):return {}
            try:
                wait(lambda:events.exists());send(['seek',5,'absolute+exact'])
                wait(lambda:progress(0) and .24<progress(0)[0]<.27)
                send(['keypress','>']);wait(lambda:last().get('path')==str(root/'1.wav'))
                send(['seek',7,'absolute+exact']);wait(lambda:progress(1) and .69<progress(1)[0]<.72)
                self.assertAlmostEqual(progress(0)[1],5,delta=.15)
                send(['keypress','<']);wait(lambda:last().get('path')==str(root/'0.wav') and 4.9<last().get('position',0)<5.2)
                self.assertAlmostEqual(progress(1)[1],7,delta=.15)
                send(['keypress','>']);wait(lambda:last().get('path')==str(root/'1.wav'))
                send(['seek',9.8,'absolute+exact']);send(['set','pause',False])
                wait(lambda:progress(1) and progress(1)[0]==1,3)
                self.assertIsNone(proc.poll(),'held EOF keeps the player available')
                self.assertAlmostEqual(progress(0)[1],5,delta=.15)
                status=(root/'state/newsboat/download-status.tsv.watched').read_text()
                self.assertIn(URLS[1]+'\t100%',status)
                self.assertIn(URLS[0]+'\t25%',status)
                send(['keypress','<']);wait(lambda:last().get('path')==str(root/'0.wav'))
                self.assertEqual(progress(1)[0],1,'leaving a completed video preserves 100%')
            finally:
                proc.terminate();proc.wait(timeout=4)
