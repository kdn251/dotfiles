"""The local playback handoff preserves the title displayed by mpv."""
import json, os, shutil, socket, subprocess, tempfile, time, unittest, wave
from pathlib import Path

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'

@unittest.skipUnless(shutil.which('mpv'),'requires mpv')
class PlayerTitleTests(unittest.TestCase):
    def test_local_handoff_retains_media_title(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.wav';target=root/'video-id.wav';ipc=root/'ipc'
            with wave.open(str(source),'wb') as f:
                f.setnchannels(1);f.setsampwidth(2);f.setframerate(8000);f.writeframes(b'\0'*16000)
            shutil.copyfile(source,target)
            notify=root/'notify-send';notify.write_text('#!/bin/sh\nexit 0\n');notify.chmod(0o755)
            process=subprocess.Popen(['mpv','--no-config','--vo=null','--ao=null','--pause','--idle=yes',
                '--input-ipc-server='+str(ipc),'--script='+str(SCRIPTS/'newsboat-local-playback.lua'),str(source)],
                env=dict(os.environ,PATH=str(root)+os.pathsep+os.environ['PATH']),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                end=time.monotonic()+5
                while not ipc.exists() and time.monotonic()<end:time.sleep(.02)
                connection=socket.socket(socket.AF_UNIX);connection.settimeout(3);connection.connect(str(ipc))
                stream=connection.makefile('rwb',buffering=0)
                def command(args):
                    stream.write((json.dumps({'command':args,'request_id':1})+'\n').encode())
                    while True:
                        row=json.loads(stream.readline())
                        if row.get('request_id')==1:return row
                command(['script-message-to','newsboat_local_playback','switch',str(source),str(target),'0','A real video title','', 'youtube'])
                end=time.monotonic()+3
                while time.monotonic()<end:
                    if command(['get_property','path']).get('data')==str(target):break
                    time.sleep(.02)
                self.assertEqual(command(['get_property','path']).get('data'),str(target))
                self.assertEqual(command(['get_property','media-title']).get('data'),'A real video title')
                stream.close();connection.close()
            finally:
                process.terminate();process.wait(timeout=5)
