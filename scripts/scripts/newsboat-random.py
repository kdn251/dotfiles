#!/usr/bin/env python3
"""Random Starred pick; ask whether to keep it after its window closes."""
import fcntl
import html
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS/f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def notify(title, text):
    subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '6000', title, html.escape(text)], check=False)


def choose(rows):
    # A URL can appear under multiple feeds; each distinct item gets one chance.
    unique = {r['url']: r for r in rows if urlparse(r.get('url', '')).scheme in {'http', 'https'}}
    return secrets.choice(list(unique.values())) if unique else None


def clients():
    return json.loads(subprocess.check_output(['hyprctl', 'clients', '-j'], timeout=5))


def browser_host(url):
    from newsboat_articles import find
    if find(url):
        return '127.0.0.1'
    host = (urlparse(url).hostname or '').lower()
    return 'old.reddit.com' if host in {'reddit.com', 'www.reddit.com', 'np.reddit.com', 'new.reddit.com'} else host


def new_browser_window(windows, previous, host):
    matches = [w['address'] for w in windows if w['address'] not in previous
               and any(w.get(field, '').startswith(f'brave-{host}__') for field in ('class', 'initialClass'))]
    if len(matches) > 1:
        raise ValueError('More than one matching browser window opened. Keeping the item starred.')
    return matches[0] if matches else None


def wait_for_browser(previous, host):
    deadline = time.monotonic() + 120
    address = None
    while time.monotonic() < deadline:
        address = new_browser_window(clients(), previous, host)
        if address:
            break
        time.sleep(.1)
    if not address:
        raise ValueError('Could not identify the article window. The item is still starred.')
    while any(w['address'] == address for w in clients()):
        time.sleep(.4)


def wait_for_video(path):
    deadline = time.monotonic() + 120
    playing = False
    while True:
        try:
            state = path.read_text()
        except FileNotFoundError:
            state = ''
        if state == 'closed':
            return
        if state == 'failed':
            raise ValueError('Playback did not start. The item is still starred.')
        playing = playing or state == 'playing'
        if not playing and time.monotonic() >= deadline:
            raise ValueError('Playback did not start in time. The item is still starred.')
        time.sleep(.2)


def ask_to_unstar(row, starred):
    from newsboat_random_prompt import request_choice
    if request_choice(row) == 'unstar':
        starred.enqueue_star(row['url'], False)


def run():
    if not os.environ.get('NEWSBOAT_RANDOM_PROMPT_DIR'):
        raise ValueError('Restart Newsboat through newsboat-launch.sh to use the in-terminal prompt.')
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'random-pick.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            notify('🍀 Random Starred item', 'Close your current random pick and answer its Unstar / Keep starred prompt first.')
            return
        starred = module('newsboat-starred')
        row = choose(starred.view_entries())
        if not row:
            notify('Starred is empty', 'Star something with s, then press 7 on the main screen.')
            return
        opener = module('newsboat-open')
        url = row['url']
        with tempfile.TemporaryDirectory(prefix='newsboat-random-') as directory:
            env = dict(os.environ)
            media = opener.launcher_for(url) == 'newsboat-play-video.sh'
            if media:
                lifecycle = Path(directory)/'lifecycle'
                env['NEWSBOAT_RANDOM_LIFECYCLE'] = str(lifecycle)
                command = [str(SCRIPTS/'newsboat-play-video.sh'), url, row.get('title', '')]
            else:
                previous = {w['address'] for w in clients()}
                host = browser_host(url)
                command = [sys.executable, str(SCRIPTS/'newsboat-open.py'), url]
            subprocess.Popen(command, env=env, start_new_session=True,
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if media:
                wait_for_video(lifecycle)
            else:
                wait_for_browser(previous, host)
        ask_to_unstar(row, starred)


if __name__ == '__main__':
    try:
        run()
    except Exception as error:
        notify('🍀 Random pick unavailable', str(error))
        sys.exit(1)
