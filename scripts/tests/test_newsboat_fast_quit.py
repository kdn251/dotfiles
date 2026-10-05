"""Quit remains responsive even when a download holds the library lock."""
import fcntl
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

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'


class FastQuitTests(unittest.TestCase):
    def test_old_background_sample_cannot_undo_reset(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(watch,'STATE',Path(folder)),patch.object(media,'STATE',Path(folder)/'downloads'),patch('newsboat_playthroughs.with_group_progress',side_effect=lambda value:value):
            url='https://youtu.be/abcdefghijk'
            watch.record(url,50,100,sampled_at=10)
            watch.record(url,0,1,sampled_at=20)
            watch.record(url,70,100,sampled_at=15)
            self.assertEqual(watch.resume_position(url),0)
            self.assertIn('\t0%',(Path(folder)/'download-status.tsv.watched').read_text())

    def test_quit_does_not_wait_for_busy_library_and_final_position_survives(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);state=root/'newsboat';downloads=state/'downloads';downloads.mkdir(parents=True)
            sample=root/'sample.wav';ipc=root/'ipc';url='https://youtu.be/abcdefghijk'
            with wave.open(str(sample),'wb') as out:
                out.setnchannels(1);out.setsampwidth(2);out.setframerate(8000);out.writeframes(b'\0'*16000*60)
            proc=subprocess.Popen(['mpv','--no-config','--pause','--ao=null','--vo=null','--start=30','--input-ipc-server='+str(ipc),'--script='+str(SCRIPTS/'newsboat-watch-completion.lua'),str(sample)],env=dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_CACHE=str(root/'missing-cache'),NEWSBOAT_MEDIA_URL=url,NEWSBOAT_MAINTENANCE=str(SCRIPTS/'newsboat-maintenance.py')),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                deadline=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<deadline:time.sleep(.02)
                with socket.socket(socket.AF_UNIX) as sock:
                    sock.settimeout(3);sock.connect(str(ipc))
                    with sock.makefile('rwb',buffering=0) as stream:
                        while time.monotonic()<deadline:
                            stream.write(b'{"command":["get_property","time-pos"],"request_id":1}\n')
                            while True:
                                reply=json.loads(stream.readline())
                                if reply.get('request_id')==1:break
                            if reply.get('data',0)>=29:break
                            time.sleep(.05)
                        time.sleep(.2)  # Let the file-loaded resume handler finish.
                        with (downloads/'.library.lock').open('w') as lock:
                            fcntl.flock(lock,fcntl.LOCK_EX)
                            started=time.monotonic()
                            stream.write(b'{"command":["quit-watch-later"]}\n')
                            proc.wait(timeout=1)
                            self.assertLess(time.monotonic()-started,1)
                            self.assertFalse((state/'watch-progress.db').exists())
                        deadline=time.monotonic()+5
                        position=None
                        while time.monotonic()<deadline:
                            try:
                                with sqlite3.connect(state/'watch-progress.db') as db:
                                    row=db.execute('SELECT position FROM progress').fetchone()
                                    if row:position=row[0]
                            except sqlite3.Error:pass
                            if position is not None:break
                            time.sleep(.05)
                        self.assertIsNotNone(position)
                        self.assertGreaterEqual(position,29)
            finally:
                if proc.poll() is None:proc.kill();proc.wait()
