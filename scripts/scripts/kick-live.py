#!/usr/bin/env python3
"""Kick live-only lookup, avatars and the stream picker's background cache."""
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from stream_profile import cache_avatar
from stream_live_cache import OfflineError, update_live_list, menu


def resolve(data):
    if not isinstance(data, dict) or 'livestream' not in data:
        raise ValueError('Kick returned an unrecognized channel response.')
    live = data['livestream']
    # Offline channels still expose a playback URL. Never treat that as live.
    if live is None or (isinstance(live, dict) and live.get('is_live') is False):
        raise OfflineError('This channel is offline on Kick.')
    if not isinstance(live, dict) or not live:
        raise ValueError('Kick returned an invalid live status.')
    url = live.get('playback_url') or data.get('playback_url')
    if not isinstance(url, str) or urlparse(url).scheme != 'https':
        raise ValueError('This Kick broadcast has no public playable stream.')
    return dict(url=url, title=live.get('session_title') or 'Kick live stream')


def fetch(channel):
    parsed = urlparse(channel)
    slug = parsed.path.strip('/').lower()
    if parsed.scheme != 'https' or parsed.hostname not in ('kick.com', 'www.kick.com') or not re.fullmatch(r'[a-z0-9_-]+', slug):
        raise ValueError('Expected a Kick channel URL.')
    channel = 'https://kick.com/' + slug
    request = Request('https://kick.com/api/v2/channels/' + slug,
                      headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json', 'Referer': channel})
    with urlopen(request, timeout=15) as response:
        data = json.loads(response.read(8 * 1024 * 1024))
    if not isinstance(data, dict):
        raise ValueError('Kick returned an invalid channel response.')
    icon = cache_avatar(channel, (data.get('user') or {}).get('profile_pic') or '')
    return dict(resolve(data), icon=icon)


def main():
    cache = Path.home() / '.cache/kick-live.json'
    if sys.argv[1:] == ['--update']:
        update_live_list(Path.home() / 'scripts/kick_channels.tsv', cache, fetch)
    elif sys.argv[1:] == ['--menu']:
        menu(cache, 'Kick')
    else:
        print(json.dumps(fetch(sys.argv[1])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
