#!/usr/bin/env python3
"""Run normal bookkeeping/downloads after an in-window video transition."""
import os
from pathlib import Path
import subprocess
import sys
from newsboat_last_opened import mark

url=sys.argv[1]
scripts=Path(__file__).resolve().parent
mark(url)
subprocess.run([sys.executable,str(scripts/'newsboat-history.py'),'record',url,'video'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
env=dict(os.environ,NEWSBOAT_REUSE_PLAYER='1',NEWSBOAT_MEDIA_URL=url)
env.pop('NEWSBOAT_PLAY_READY',None)
subprocess.Popen([str(scripts/'mpv-yt'),url],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
