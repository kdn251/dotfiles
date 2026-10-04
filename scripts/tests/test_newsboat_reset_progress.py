import importlib.util
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import time
import unittest
import wave
from unittest.mock import patch
import newsboat_media as media
import newsboat_watch_progress as watch
import newsboat_reading as reading
import newsboat_browser_reading as browser
import newsboat_download_cleanup as cleanup

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('reset',SCRIPTS/'newsboat-reset-progress.py')
reset=importlib.util.module_from_spec(spec);spec.loader.exec_module(reset)


class ResetTests(unittest.TestCase):
    def test_video_alias_progress_cleanup_and_zero_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            url='https://www.youtube.com/watch?v=abcdefghijk'
            with patch.object(watch,'STATE',root),patch.object(media,'STATE',root/'downloads'),patch.object(cleanup,'STATE',root),patch('newsboat_playthroughs.with_group_progress',side_effect=lambda value:value):
                watch.record(url,80,100)
                with cleanup.database() as db:
                    db.execute('INSERT INTO watched VALUES (?,?,?,?,?)',('/video.mp4',url,1,1,1))
                reset.reset('https://youtu.be/abcdefghijk')
                self.assertEqual(watch.resume_position(url),0)
                self.assertIn(url+'\t0%',(root/'download-status.tsv.watched').read_text())
                with cleanup.database() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM watched').fetchone()[0],0)
                self.assertEqual(watch.resume_position('https://youtu.be/zzzzzzzzzzz',missing=-1),-1)

    def test_resets_original_and_downloaded_article_anchors(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(reading,'STATE',Path(folder)):
            url='http://www.example.org/essay'
            browser.register(url)
            with browser.database() as db:
                db.execute('UPDATE articles SET fraction=.8,position=?',(json.dumps(dict(y=500,anchor=2,offset=10)),))
                db.execute('UPDATE browser_articles SET position=?',(json.dumps(dict(y=700,anchor=4,offset=20)),))
            reset.reset('https://example.org/essay')
            saved=browser.handle(dict(action='get',url=url))
            self.assertEqual(saved['fraction'],0)
            self.assertEqual(saved['position'],{})
            with browser.database() as db:self.assertEqual(db.execute('SELECT position FROM articles').fetchone()[0],'{}')
            self.assertIn('\t0%',(Path(folder)/'download-status.tsv.read').read_text())

    def test_mpv_stale_start_is_overridden_by_reset(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'newsboat';state.mkdir()
            url='https://www.youtube.com/watch?v=abcdefghijk'
            with sqlite3.connect(state/'watch-progress.db') as db:
                db.execute('CREATE TABLE progress(identity TEXT PRIMARY KEY,url TEXT,fraction REAL,position REAL,duration REAL)')
                db.execute('INSERT INTO progress VALUES (?,?,?,?,?)',('youtube:abcdefghijk',url,0,0,60))
            sample=root/'sample.wav';ipc=root/'ipc'
            with wave.open(str(sample),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*16000*60)
            proc=subprocess.Popen(['mpv','--no-config','--pause','--ao=null','--vo=null','--start=30','--input-ipc-server='+str(ipc),'--script='+str(SCRIPTS/'newsboat-watch-completion.lua'),str(sample)],env=dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_MEDIA_URL=url,NEWSBOAT_MAINTENANCE=str(SCRIPTS/'newsboat-maintenance.py')),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<deadline:time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(3);sock.connect(str(ipc))
                    with sock.makefile('rwb',buffering=0) as stream:
                        position=None
                        while time.monotonic()<deadline:
                            stream.write(b'{"command":["get_property","time-pos"],"request_id":1}\n')
                            while True:
                                reply=json.loads(stream.readline())
                                if reply.get('request_id')==1:break
                            position=reply.get('data')
                            if position is not None and position<1:break
                            time.sleep(.05)
                        self.assertIsNotNone(position)
                        self.assertLess(position,1)
            finally:
                proc.terminate();proc.wait(timeout=5)
