#!/usr/bin/env python3
"""o/O: play YouTube videos and Twitch streams/VODs; open other links in Brave."""
import os
from pathlib import Path
import sys
import re
from urllib.parse import urlparse
from newsboat_media import identity


def launcher_for(url):
    video = identity(url)
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    channel = parsed.path.strip('/')
    twitch_live = (
        parsed.scheme in {'http', 'https'}
        and host in {'twitch.tv', 'www.twitch.tv', 'm.twitch.tv'}
        and re.fullmatch(r'[A-Za-z0-9_]+', channel) is not None
        and channel.lower() not in {'directory', 'downloads', 'settings', 'subscriptions',
                                    'inventory', 'wallet', 'login', 'signup', 'search', 'videos',
                                    'jobs', 'p', 'turbo', 'drops'}
    )
    playable = (video and video[0] in {'youtube', 'twitch'}) or twitch_live
    return 'newsboat-play-video.sh' if playable else 'newsboat-brave-app.sh'


if __name__ == '__main__':
    url = sys.argv[1]
    launcher = Path(__file__).resolve().with_name(launcher_for(url))
    if launcher.name == 'newsboat-brave-app.sh':
        from newsboat_articles import find
        local = find(url)
        if local:
            os.environ['NEWSBOAT_HISTORY_URL'] = url
            from newsboat_reading import reader_url
            url = reader_url(url)
    os.execv(str(launcher), [str(launcher), url])
