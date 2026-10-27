#!/usr/bin/env python3
"""Send menu rows to a warm picker process; start it if needed."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

path = str(Path(os.environ['XDG_RUNTIME_DIR'])/'stream-picker.sock')
data = sys.stdin.read()
started = False
for attempt in range(100):
    client = socket.socket(socket.AF_UNIX)
    try:
        client.connect(path)
        break
    except (FileNotFoundError, ConnectionRefusedError):
        client.close()
        if not started:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('stream-picker.py')), '--daemon'],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True)
            started = True
        time.sleep(.02)
else:
    raise SystemExit('Stream picker did not start')
with client:
    client.sendall((json.dumps(data)+'\n').encode())
    with client.makefile('r') as response:
        value = json.loads(response.readline() or '""')
        if value:
            print(value)
