import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
import wave

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('ipc',SCRIPTS/'twitch-player-ipc.py')
ipc=importlib.util.module_from_spec(spec);spec.loader.exec_module(ipc)

class ReuseTests(unittest.TestCase):
    def test_reuse_updates_identity_title_readiness_and_quit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);audio=root/'test.wav';marker=root/'ready'
            with wave.open(str(audio),'wb') as wav:
                wav.setparams((1,2,8000,0,'NONE','not compressed'))
                wav.writeframes(b'\0\0'*8000*10)
            ipc.SOCKET=str(root/'ipc')
            player=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null',
                '--loop-file=inf','--input-ipc-server='+ipc.SOCKET,
                '--script='+str(SCRIPTS/'twitch-first-frame.lua'),str(audio)],
                env=dict(os.environ,TWITCH_FIRST_FRAME=str(marker),TWITCH_STREAMER_USERNAME='first'),
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            def ready():
                until=time.monotonic()+5
                while time.monotonic()<until:
                    if marker.exists() and marker.read_text()=='playing':return
                    time.sleep(.02)
                self.fail('No first-frame signal')
            waiter=None
            try:
                ready();self.assertEqual(ipc.channel(player.pid),'first')
                client,_=ipc.connect()
                with client,client.makefile('rwb',buffering=0) as stream:
                    ipc.command(stream,'set_property','pause',True)
                marker.unlink()
                self.assertEqual(ipc.reuse('second','Second stream',str(audio),str(marker)),player.pid)
                ready();self.assertEqual(ipc.channel(player.pid),'second')
                client,_=ipc.connect()
                with client,client.makefile('rwb',buffering=0) as stream:
                    self.assertEqual(ipc.command(stream,'get_property','media-title'),'Second stream')
                    self.assertFalse(ipc.command(stream,'get_property','pause'))
                waiter=subprocess.Popen(['python',str(SCRIPTS/'twitch-player-ipc.py'),'wait',str(player.pid)])
                time.sleep(.1)
                self.assertIsNone(waiter.poll())
                player.terminate();player.wait(timeout=3)
                self.assertEqual(waiter.wait(timeout=3),0)
            finally:
                if player.poll() is None:player.terminate();player.wait(timeout=3)
                if waiter and waiter.poll() is None:waiter.terminate();waiter.wait(timeout=3)

if __name__=='__main__':unittest.main()
