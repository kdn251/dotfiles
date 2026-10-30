#!/usr/bin/env python3
"""Open the public stream page, never MPV's signed media/CDN URL."""
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


def valid_page(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname in
            {'twitch.tv', 'www.twitch.tv', 'kick.com', 'www.kick.com',
             'youtube.com', 'www.youtube.com', 'rumble.com', 'www.rumble.com'}
            and not parsed.username and not parsed.password
            and not parsed.path.lower().endswith(('.m3u8', '.mpd')))


def open_page(url):
    if not valid_page(url): return False
    browser = shutil.which('brave') or shutil.which('brave-browser')
    if not browser: return False
    subprocess.Popen([browser, '--new-tab', url], stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return True


if __name__ == '__main__':
    raise SystemExit(0 if len(sys.argv) == 2 and open_page(sys.argv[1]) else 1)
