"""Small authenticated Miniflux client; never log credentials."""
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
import urllib.request


class Client:
    def __init__(self):
        config = Path(os.environ.get('NEWSBOAT_MINIFLUX_CONFIG', Path.home()/'.newsboat/miniflux_creds.conf'))
        values = {}
        for line in config.read_text().splitlines():
            tokens = shlex.split(line, comments=True)
            if len(tokens) > 1:
                values[tokens[0]] = tokens[1]
        password = values.get('miniflux-password')
        if password is None:
            password = subprocess.check_output(values['miniflux-passwordeval'], shell=True, text=True, timeout=10).strip()
        self.base = values['miniflux-url'].rstrip('/')
        self.auth = 'Basic ' + base64.b64encode((values['miniflux-login'] + ':' + password).encode()).decode()

    def request(self, path, data=None, method=None):
        request = urllib.request.Request(self.base + '/v1/' + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization': self.auth, 'Content-Type': 'application/json'}, method=method)
        with urllib.request.urlopen(request, timeout=15) as response:
            body = response.read()
            return json.loads(body) if body else None

    def starred(self):
        entries = []
        offset = 0
        while True:
            result = self.request(f'entries?starred=true&limit=100&offset={offset}')
            entries.extend(result['entries'])
            offset += len(result['entries'])
            if offset >= result['total']:
                return entries
            if not result['entries']:
                raise RuntimeError('Incomplete response for starred items')
