#!/usr/bin/env python3
"""Prepare a cached BGRA thumbnail for mpv without blocking playback."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from PIL import Image, ImageOps
from newsboat_thumbnails import fetch_png, video_key

WIDTH, HEIGHT = 480, 270


def prepare(url):
    ident = video_key(url)
    if not ident:
        raise ValueError('No video thumbnail available')
    root = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'newsboat/up-next'
    root.mkdir(parents=True, exist_ok=True)
    path = root/(hashlib.sha256(ident.encode()).hexdigest()+'.bgra')
    if not path.exists() or path.stat().st_size != WIDTH*HEIGHT*4:
        with Image.open(io.BytesIO(fetch_png(ident))) as image:
            image = ImageOps.pad(image.convert('RGBA'), (WIDTH, HEIGHT), color=(30,30,46,255))
            # mpv expects premultiplied BGRA; flatten the rounded source border.
            background = Image.new('RGBA', image.size, (30,30,46,255))
            background.alpha_composite(image)
            data = background.tobytes('raw', 'BGRA')
        temporary = path.with_suffix('.'+str(os.getpid())+'.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
    return dict(path=str(path), width=WIDTH, height=HEIGHT)


if __name__ == '__main__':
    try:
        print(json.dumps(prepare(sys.argv[1])))
    except Exception:
        # The text countdown still works offline or when a thumbnail is missing.
        sys.exit(1)
