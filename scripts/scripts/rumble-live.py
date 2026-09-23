#!/usr/bin/env python3
"""Resolve a channel's current public live broadcast without selecting a replay."""
import json
import sys
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urlparse
from urllib.request import Request, urlopen


class ChannelData(HTMLParser):
    def __init__(self):
        super().__init__()
        self.capture = False
        self.parts = []
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.capture = dict(attrs).get('type') == 'application/json'
            self.parts = []

    def handle_data(self, data):
        if self.capture:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.capture:
            self.capture = False
            try:
                data = json.loads(''.join(self.parts))
                if isinstance(data, dict) and isinstance(data.get('items'), list):
                    self.items.extend(data['items'])
            except ValueError:
                pass


from stream_profile import cache_avatar
from stream_live_cache import OfflineError, update_live_list, menu


def resolve(html, channel):
    parser = ChannelData()
    parser.feed(html)
    if not parser.items:
        raise ValueError('Could not read the Rumble channel. Its page format may have changed.')
    for item in parser.items:
        if not isinstance(item, dict):
            continue
        if item.get('by', {}).get('url', '').rstrip('/').lower() != channel.rstrip('/').lower():
            continue
        if item.get('live') is not True or item.get('live_placeholder'):
            continue
        for video in item.get('videos', []):
            url = video.get('url', '')
            if video.get('type') == 'hls' and urlparse(url).scheme == 'https':
                return {'url': url, 'title': item.get('title') or 'Rumble live stream'}
        raise ValueError('The live broadcast has no public playable stream available.')
    raise OfflineError('This channel is offline on Rumble. Try again when the stream is live.')


def fetch(channel):
    channel = channel.rstrip('/')
    if urlparse(channel).hostname != 'rumble.com':
        raise ValueError('Expected a rumble.com channel URL.')
    request = Request(channel, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(request, timeout=20) as response:
        html = response.read(8 * 1024 * 1024).decode('utf-8')
    parser = ChannelData()
    parser.feed(html)
    avatar = next((item.get('by', {}).get('thumb', '') for item in parser.items
                   if item.get('by', {}).get('url', '').rstrip('/').lower() == channel.lower()), '')
    icon = cache_avatar(channel, avatar)
    return dict(resolve(html, channel), icon=icon)




def main():
    if sys.argv[1:] == ['--update']:
        update_live_list(Path.home() / 'scripts/rumble_channels.tsv',
                         Path.home() / '.cache/rumble-live.json', fetch)
    elif sys.argv[1:] == ['--menu']:
        menu(Path.home() / '.cache/rumble-live.json', 'Rumble')
    else:
        print(json.dumps(fetch(sys.argv[1])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
