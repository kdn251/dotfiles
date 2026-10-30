#!/usr/bin/env python3
"""Private, resident Twitch resolver; each worker owns its HTTP session."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time


def root():
    path = Path(os.environ['XDG_RUNTIME_DIR']) / 'twitch-stream-urls'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def request(name):
    if not re.fullmatch(r'[a-z0-9_]{1,25}', name):
        raise ValueError('Invalid channel')
    path = root() / 'resolver.sock'
    client = socket.socket(socket.AF_UNIX)
    with client:
        client.settimeout(10)
        try:
            client.connect(str(path))
        except (FileNotFoundError, ConnectionRefusedError):
            subprocess.Popen([sys.executable, __file__, '--daemon'],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            deadline = time.monotonic() + 2
            while True:
                try:
                    client.connect(str(path))
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Resolver startup timed out')
                    time.sleep(.02)
        client.sendall((name + '\n').encode())
        with client.makefile('rb') as stream:
            response = json.loads(stream.readline(4 * 1024 * 1024))
        if 'streams' not in response:
            raise ValueError('Resolution failed')
        return response


def load_fetch():
    spec = importlib.util.spec_from_file_location('resolver_url',
                Path(__file__).with_name('twitch-stream-url.py'))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    return helper.fetch


def serve():
    directory = root()
    with (directory / 'resolver.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        from streamlink import Streamlink
        fetch = load_fetch()
        local = threading.local()

        def handle(client):
            with client:
                client.settimeout(10)
                try:
                    with client.makefile('rb') as stream:
                        name = stream.readline(128).decode().strip()
                    if not re.fullmatch(r'[a-z0-9_]{1,25}', name):
                        raise ValueError('Invalid channel')
                    if not hasattr(local, 'session'):
                        local.session = Streamlink({'http-timeout': 4}, plugins_builtin=False)
                    result = fetch(name, local.session)
                except Exception:
                    # Never send tokens, signed URLs from exceptions, or tracebacks.
                    result = {'error': 'Resolution failed'}
                try:
                    client.sendall((json.dumps(result) + '\n').encode())
                except OSError:
                    pass

        path = directory / 'resolver.sock'
        path.unlink(missing_ok=True)
        with socket.socket(socket.AF_UNIX) as server, ThreadPoolExecutor(max_workers=4) as pool:
            server.bind(str(path))
            path.chmod(0o600)
            server.listen(16)
            while True:
                client, _ = server.accept()
                pool.submit(handle, client)


if __name__ == '__main__':
    serve()
