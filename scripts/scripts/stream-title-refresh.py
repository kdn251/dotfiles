#!/usr/bin/env python3
"""Refresh display metadata only; never resolve or replace playing media."""
import json
import re
import sys
import time
from urllib.request import Request, urlopen

from stream_menu_metadata import format_playback_title, load


def refresh(name, service):
    if service == 'Twitch':
        if not re.fullmatch(r'[A-Za-z0-9_]{1,25}', name):
            return ''
        query = 'query{user(login:' + json.dumps(name.lower()) + '){stream{title viewersCount game{displayName}}}}'
        request = Request('https://gql.twitch.tv/gql',
                          data=json.dumps({'query': query}).encode(),
                          headers={'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
                                   'Content-Type': 'application/json'})
        with urlopen(request, timeout=5) as response:
            stream = (json.loads(response.read(1024 * 1024)).get('data', {}).get('user') or {}).get('stream')
        if not stream:
            return ''
        data = {'title': stream.get('title'), 'viewer_count': stream.get('viewersCount'),
                'category': (stream.get('game') or {}).get('displayName')}
    else:
        # Other platforms already refresh their metadata in the live-list job.
        # Consume those updates without starting another expensive extraction.
        data = load().get(service[:1].lower(), {}).get(name.casefold(), {})
        if time.time() - data.get('checked_at', 0) > 900:
            return ''
    if not data.get('title') and not data.get('category'):
        return ''
    return format_playback_title(name, data)


if __name__ == '__main__':
    try:
        print(refresh(*sys.argv[1:]))
    except (OSError, ValueError, TypeError, AttributeError):
        # Keep the last good title through temporary network/API failures.
        pass
