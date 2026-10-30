#!/usr/bin/env python3
"""Prepare cached streamer portraits for MPV's bitmap overlay (no network)."""
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
from PIL import Image, ImageDraw, ImageOps
from stream_menu_metadata import load
from stream_profile import cache_avatar
from urllib.request import Request, urlopen


def prepare(service, name):
    if service not in ('Twitch', 'Kick', 'YouTube', 'Rumble') or not name:
        return ''
    if service == 'Twitch':
        if not re.fullmatch(r'[A-Za-z0-9_]{1,25}', name): return ''
        source = Path.home()/'.cache/twitch-profiles'/f'{name.lower()}.png'
        if not source.is_file():
            channel = 'https://www.twitch.tv/' + name.lower()
            cached = cache_avatar(channel, '')
            if not cached:
                query = 'query{user(login:' + json.dumps(name.lower()) + '){profileImageURL(width:150)}}'
                request = Request('https://gql.twitch.tv/gql',
                                  data=json.dumps({'query': query}).encode(),
                                  headers={'Client-Id': 'kimne78kx3ncx6brgo4mv6wki5h1ko',
                                           'Content-Type': 'application/json'})
                with urlopen(request, timeout=5) as response:
                    user = json.loads(response.read(1024*1024)).get('data', {}).get('user') or {}
                cached = cache_avatar(channel, user.get('profileImageURL') or '')
            source = Path(cached or '/nonexistent')
    else:
        data = load().get(service[0].lower(), {}).get(name.casefold(), {})
        if not data.get('icon'):
            try:
                selected = json.loads((Path.home()/f'.cache/{service.lower()}-live-player.json').read_text())
                if selected.get('name', '').casefold() == name.casefold():
                    data = selected
            except (OSError, ValueError): pass
        source = Path(data.get('icon') or '/nonexistent')
    if not source.is_file(): return ''
    fingerprint = f'{source}:{source.stat().st_mtime_ns}:rounded-v1'
    target = Path.home()/'.cache/mpv-stream-portraits'/(hashlib.sha256(fingerprint.encode()).hexdigest()+'.bgra')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = ImageOps.fit(image.convert('RGBA'), (192, 192), method=Image.Resampling.LANCZOS)
            mask = Image.new('L', image.size)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, 191, 191), radius=24, fill=255)
            image.putalpha(mask)
            image = image.resize((96, 96), Image.Resampling.LANCZOS)
            # MPV expects premultiplied BGRA pixels.
            pixels = bytearray()
            rgba = image.tobytes()
            for offset in range(0, len(rgba), 4):
                red, green, blue, alpha = rgba[offset:offset+4]
                pixels.extend((blue*alpha//255, green*alpha//255, red*alpha//255, alpha))
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
                output.write(pixels)
                temporary = Path(output.name)
            temporary.replace(target)
    return str(target)


if __name__ == '__main__':
    try: print(prepare(*sys.argv[1:]))
    except (OSError, ValueError): pass
