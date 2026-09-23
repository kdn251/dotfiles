"""Persist the last item launched, independently of player/window lifetime."""
import os
import tempfile
from pathlib import Path


def mark(url):
    if not url or any(c in url for c in '\r\n'):
        return
    path = Path(os.environ.get('NEWSBOAT_LAST_OPENED',
        Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/last-opened'))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix='.last-opened-', dir=path.parent)
        with os.fdopen(fd, 'w') as output:
            output.write(url + '\n')
        os.replace(temporary, path)
    except OSError:
        pass  # Recording the marker must never prevent opening an item.
