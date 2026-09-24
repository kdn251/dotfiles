#!/usr/bin/env python3
"""Edit persistent per-item plain-text notes and publish nonempty-note badges."""
import fcntl
import hashlib
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from urllib.parse import urlparse
from newsboat_media import atomic_write


def notes_dir():
    return Path(os.environ.get('XDG_DATA_HOME', Path.home()/'.local/share'))/'newsboat/notes'


def status_path():
    return Path(os.environ.get('NEWSBOAT_NOTES_STATUS',
        Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/noted-urls.txt'))


def publish():
    root = notes_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (root/'.index.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        urls = set()
        for mapping in root.glob('*.url'):
            try:
                if mapping.with_suffix('.txt').read_text().strip():
                    url = mapping.read_text().strip()
                    if url and not any(c in url for c in '\r\n'):
                        urls.add(url)
            except (OSError, UnicodeError):
                continue
        atomic_write(status_path(), ''.join(url+'\n' for url in sorted(urls)))


def edit(url):
    if urlparse(url).scheme not in {'http', 'https'} or any(c in url for c in '\r\n'):
        raise ValueError('Select an article or video to write a note.')
    root = notes_dir()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = root/(hashlib.sha256(url.encode()).hexdigest()+'.txt')
    atomic_write(path.with_suffix('.url'), url+'\n')
    path.touch(mode=0o600, exist_ok=True)
    editor = shlex.split(os.environ.get('VISUAL') or os.environ.get('EDITOR') or
                        ('nvim' if shutil.which('nvim') else 'vi'))
    try:
        return subprocess.call([*editor, str(path)])
    finally:
        publish()


if __name__ == '__main__':
    try:
        if sys.argv[1:] == ['--refresh']:
            publish()
        else:
            sys.exit(edit(sys.argv[1]))
    except (OSError, ValueError, IndexError) as error:
        subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '5000', 'Notes unavailable', str(error)])
        sys.exit(1)
