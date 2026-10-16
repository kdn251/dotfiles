"""Play an LSF submission alongside its page, scoped to that page's lifetime."""
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from html.parser import HTMLParser
from urllib.parse import urlparse

SCRIPTS = Path(__file__).resolve().parent


def post_id(url):
    p = urlparse(url)
    if p.scheme not in {'http', 'https'} or p.hostname not in {
        'reddit.com', 'www.reddit.com', 'old.reddit.com', 'new.reddit.com',
        'np.reddit.com', 'm.reddit.com',
    }:
        return None
    m = re.match(r'^/r/livestreamfail/comments/([a-z0-9]+)(?:/|$)', p.path, re.I)
    return m.group(1).lower() if m else None


class SubmittedLink(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = None
        self.label = ''
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.label = ''

    def handle_data(self, data):
        if self.href:
            self.label += data

    def handle_endtag(self, tag):
        if tag == 'a':
            if self.label.strip() == '[link]' and self.href:
                self.links.append(self.href)
            self.href = None


def playable(url):
    p = urlparse(url)
    if p.scheme not in {'http', 'https'}:
        return None
    if p.hostname == 'v.redd.it' and re.fullmatch(r'/[a-zA-Z0-9]+/?', p.path):
        return url.rstrip('/') + '/DASHPlaylist.mpd'
    from newsboat_media import identity
    if identity(url) or p.hostname in {'kick.com', 'www.kick.com'} and '/clips/' in p.path:
        return url
    return None


def submission(url):
    cache = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))
    try:
        with sqlite3.connect(cache.as_uri() + '?mode=ro', uri=True, timeout=.3) as db:
            rows = db.execute('SELECT url,title,content FROM rss_item WHERE url LIKE ? ORDER BY id DESC',
                              ('%/comments/' + post_id(url) + '%',))
            for source, title, content in rows:
                if post_id(source) != post_id(url):
                    continue
                parser = SubmittedLink()
                parser.feed(content or '')
                for link in parser.links:
                    video = playable(link)
                    if video:
                        return video, title
    except (sqlite3.Error, OSError):
        pass
    # yt-dlp's Reddit extractor can resolve submissions absent from the cache.
    return url, 'LivestreamFail'


def clients():
    return json.loads(subprocess.check_output(['hyprctl', 'clients', '-j'], timeout=5))


def close_player(player):
    if player.poll() is None:
        player.terminate()
        try:
            player.wait(timeout=3)
        except subprocess.TimeoutExpired:
            player.kill()
            player.wait()


def run(url):
    previous = {w['address'] for w in clients()}
    subprocess.Popen([str(SCRIPTS/'newsboat-brave-app.sh'), url])
    address = None
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        matches = [w['address'] for w in clients() if w['address'] not in previous
                   and any(w.get(k, '').startswith(('brave-old.reddit.com__', 'brave-m.reddit.com__'))
                           for k in ('class', 'initialClass'))]
        if len(matches) == 1:
            address = matches[0]
            break
        time.sleep(.1)
    if not address:
        subprocess.run(['notify-send', '-a', 'Newsboat', 'Video not started',
                        'Could not identify the Reddit window.'])
        return
    video, title = submission(url)
    with tempfile.TemporaryDirectory(prefix='newsboat-reddit-') as runtime:
        env = dict(os.environ, NEWSBOAT_MEDIA_URL=url)
        player = subprocess.Popen(['mpv', '--no-terminal', '--force-window=no',
                                   '--input-ipc-server=' + runtime + '/mpv.sock',
                                   '--force-media-title=' + title,
                                   '--script=' + str(SCRIPTS/'newsboat-copy-url.lua'),
                                   '--', video], env=env)
        try:
            while player.poll() is None:
                if not any(w['address'] == address for w in clients()):
                    break
                time.sleep(.2)
        finally:
            close_player(player)


def launch(url):
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
    state.mkdir(parents=True, exist_ok=True)
    with (state/'reddit-video.log').open('a') as log:
        subprocess.Popen([sys.executable, __file__, url], stdin=subprocess.DEVNULL,
                         stdout=log, stderr=log, start_new_session=True)
    return 0


if __name__ == '__main__':
    run(sys.argv[1])
