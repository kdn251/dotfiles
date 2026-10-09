import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import unittest
import wave
from unittest.mock import patch
import newsboat_queue_panel as panel
from test_newsboat_reconnect import reader
from test_newsboat_queue import isolated, URLS
import newsboat_queue as queue

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

class TimedSnoozeTests(unittest.TestCase):
    def test_native_prompt_set_validation_cancel_and_header(self):
        with isolated() as (root,_):
            for url in URLS[:2]:queue.change('add',url)
            queue.change('stop-after',URLS[1])
            status=root/'queue';timer=Path(str(status)+'.snooze')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Test</title><link>https://example.org</link><description>Test</description><item><title>Article</title><link>https://example.org/a</link><guid>1</guid></item></channel></rss>')
            cfg='show-read-feeds yes\nconfirm-exit no\nmacro z snooze-timer\nmacro Z snooze-cancel\nbind-key , macro-prefix\n'
            with patch.dict(os.environ,NEWSBOAT_QUEUE_STATUS=str(status)):
                header=panel.Header();header.update()
                with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_QUEUE_STATUS':str(status),'NEWSBOAT_QUEUE_HEADER':str(header.path)}) as (_,screen,send,wait):
                    wait(lambda s:'Your feeds' in s)
                    send(',z');wait(lambda s:'Snooze after' in s)
                    send('1h30m\n');wait(lambda s:'Timed snooze set' in s)
                    self.assertAlmostEqual(int(timer.read_text())-time.time(),5400,delta=3)
                    header.due=0;header.update()
                    wait(lambda s:'💤 1h 30m left · after #2' in s)
                    send(',z');wait(lambda s:'Snooze after' in s)
                    before=timer.read_text();send('0m\n');wait(lambda s:'greater than zero' in s)
                    self.assertEqual(timer.read_text(),before)
                    send('\n');wait(lambda s:'Article' in s)
                    send(',Z');wait(lambda s:'Timed snooze cancelled' in s)
                    self.assertFalse(timer.exists())
                    self.assertTrue(queue.entries()[1]['stop_after'])
                    send(',z');wait(lambda s:'Snooze after' in s)
                    send('30m\n');wait(lambda s:'Timed snooze set' in s)
                    self.assertAlmostEqual(int(timer.read_text())-time.time(),1800,delta=3)

    def test_real_mpv_timer_across_skip_expiry_cancel_and_shutdown(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);scripts=root/'scripts';scripts.mkdir()
            shutil.copy(SCRIPTS/'newsboat-playlist-playback.lua',scripts)
            source=root/'video.wav'
            with wave.open(str(source),'wb') as audio:
                audio.setnchannels(1);audio.setsampwidth(2);audio.setframerate(8000);audio.writeframes(b'\0\0'*8000*30)
            plan=dict(enabled=True,queue=False,next={'url':URLS[1],'title':'Next'})
            (scripts/'newsboat_autoplay.py').write_text('import json\nprint('+repr(json.dumps(plan))+')\n')
            target=dict(url=URLS[1],title='Next',path=str(source),plan=plan)
            (scripts/'newsboat-playback-target.py').write_text('print('+repr(json.dumps(target))+')\n')
            ipc=root/'ipc';status=root/'queue';timer=Path(str(status)+'.snooze')
            marker=Path(str(status)+'.stop');marker.write_text('keep this marker')
            env=dict(os.environ,NEWSBOAT_MEDIA_URL=URLS[0],NEWSBOAT_QUEUE_STATUS=str(status))
            proc=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--idle=yes','--input-ipc-server='+str(ipc),'--script='+str(scripts/'newsboat-playlist-playback.lua'),str(source)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                until=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<until:time.sleep(.05)
                sock=socket.socket(socket.AF_UNIX);sock.settimeout(3);sock.connect(str(ipc));stream=sock.makefile('rwb',buffering=0)
                def command(*args):
                    stream.write((json.dumps({'command':args,'request_id':1})+'\n').encode())
                    while True:
                        value=json.loads(stream.readline())
                        if value.get('request_id')==1:return value.get('data')
                until=time.monotonic()+5
                while command('get_property','user-data/newsboat/autoplay') is not True and time.monotonic()<until:time.sleep(.05)
                timer.write_text(str(int(time.time())+60))
                command('keypress','>')
                until=time.monotonic()+5
                while command('get_property','user-data/newsboat/url')!=URLS[1] and time.monotonic()<until:time.sleep(.05)
                self.assertEqual(command('get_property','user-data/newsboat/url'),URLS[1])
                self.assertTrue(timer.exists(),'manual skip must preserve the deadline')
                timer.unlink();time.sleep(.4)
                self.assertTrue(command('get_property','user-data/newsboat/autoplay'))
                command('set_property','pause',True)
                timer.write_text(str(int(time.time())+1))
                until=time.monotonic()+4
                while timer.exists() and time.monotonic()<until:time.sleep(.05)
                self.assertFalse(timer.exists(),'wall-clock timer expires even while paused')
                self.assertTrue(command('get_property','pause'))
                self.assertFalse(command('get_property','user-data/newsboat/autoplay'))
                self.assertEqual(marker.read_text(),'keep this marker')
                command('set_property','pause',False)
                timer.write_text(str(int(time.time())+1))
                until=time.monotonic()+4
                while timer.exists() and time.monotonic()<until:time.sleep(.05)
                self.assertFalse(timer.exists())
                self.assertTrue(command('get_property','pause'),'timer must pause active playback too')
                timer.write_text(str(int(time.time())+60))
                command('quit');proc.wait(timeout=4)
                self.assertFalse(timer.exists(),'closing mpv cancels timed snooze')
                stream.close();sock.close()
            finally:
                if proc.poll() is None:proc.terminate();proc.wait(timeout=4)
