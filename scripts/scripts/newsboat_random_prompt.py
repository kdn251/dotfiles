"""Session-scoped, in-terminal choice after a random Starred item closes."""
import json
import os
from pathlib import Path
import secrets
import time
import unicodedata


def atomic_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def request_choice(row):
    directory = Path(os.environ['NEWSBOAT_RANDOM_PROMPT_DIR'])
    token = secrets.token_hex(16)
    request = directory/'request.json'
    answer = directory/'answer.json'
    if not directory.is_dir():
        return 'keep'
    answer.unlink(missing_ok=True)
    atomic_json(request, dict(id=token, title=row.get('title') or row['url']))
    try:
        while directory.is_dir():
            try:
                response = json.loads(answer.read_text())
                if response.get('id') == token:
                    return 'unstar' if response.get('action') == 'unstar' else 'keep'
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        return 'keep'  # The Newsboat session closed; leave its star alone.
    finally:
        request.unlink(missing_ok=True)
        answer.unlink(missing_ok=True)


def fit(text, width):
    result = ''
    used = 0
    for char in text:
        if unicodedata.category(char).startswith('C'):
            char = ' '
        cells = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in 'WF' else 1)
        if used + cells > width:
            break
        used += cells
        result += char
    return result + ' ' * (width-used)


class Prompt:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.current = None

    def poll(self):
        if self.current:
            return False
        try:
            request = json.loads((self.directory/'request.json').read_text())
            if not isinstance(request.get('title'), str) or not isinstance(request.get('id'), str):
                return False
            self.current = request
            return True
        except (OSError, ValueError):
            return False

    def handle(self, data):
        # Consume the entire input event, so dismissal cannot also act on a row.
        action = 'unstar' if data in (b'u', b'U') else 'keep' if data in (b'k', b'K', b'\r', b'\n', b'\x1b') else None
        if action is None:
            return False
        atomic_json(self.directory/'answer.json', dict(id=self.current['id'], action=action))
        (self.directory/'request.json').unlink(missing_ok=True)
        self.current = None
        return True

    def draw(self, cols, rows):
        if not self.current:
            return b''
        lines = ['🍀 Finished: ' + self.current['title'],
                 'Unstar this item?  [u] Unstar   [k / Enter / Esc] Keep starred']
        if rows < 3:
            lines = [lines[-1]]
        data = '\x1b7\x1b[?25l\x1b[0;38;5;255;48;5;235m'
        for index, line in enumerate(lines):
            data += f'\x1b[{max(1, rows-len(lines)+index+1)};1H' + fit(line, max(1, cols-1)) + '\x1b[K'
        return (data+'\x1b[0m\x1b8').encode()
