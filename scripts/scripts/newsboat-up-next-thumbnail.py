#!/usr/bin/env python3
"""Prepare a cached BGRA thumbnail for mpv without blocking playback."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
from PIL import Image, ImageOps, ImageDraw, ImageFont
from newsboat_creator_images import fetch as fetch_avatar
from newsboat_thumbnails import fetch_png, video_key

WIDTH, HEIGHT = 1280, 720


def header_card(image, title, avatar):
    canvas = Image.new('RGBA', (WIDTH, HEIGHT+144), (30,30,46,255))
    canvas.alpha_composite(image, (0,144))
    left = 16
    if avatar:
        with Image.open(io.BytesIO(avatar)) as source:
            face = ImageOps.fit(source.convert('RGBA'), (104,104), method=Image.Resampling.LANCZOS)
        mask = Image.new('L',face.size);ImageDraw.Draw(mask).ellipse((0,0,103,103),fill=255)
        canvas.paste(face,(8,20),mask)
        left = 136
    font = ImageFont.truetype('/usr/share/fonts/gsfonts/NimbusSans-Regular.otf',40)
    lines, line = [], ''
    for word in ' '.join(title.split()).split():
        if line and font.getlength(line+' '+word)>WIDTH-left-20:
            lines.append(line);line=''
        line = (line+' '+word).strip()
    if line:lines.append(line)
    lines = lines or ['Untitled video']
    if len(lines)>2:
        lines=lines[:2];lines[-1]+='…'
    for i,line in enumerate(lines):
        while font.getlength(line)>WIDTH-left-20:
            line=line[:-2]+'…'
        ImageDraw.Draw(canvas).text((left, (144-len(lines)*48)//2+i*48),line,font=font,fill='#ffffff')
    return canvas


def prepare(url, title='', creator=''):
    ident = video_key(url)
    if not ident:
        raise ValueError('No video thumbnail available')
    root = Path(os.environ.get('XDG_CACHE_HOME', Path.home()/'.cache'))/'newsboat/up-next'
    root.mkdir(parents=True, exist_ok=True)
    path = root/(hashlib.sha256((ident+'\n'+title).encode()).hexdigest()+'.bgra')
    height = HEIGHT+144 if title else HEIGHT
    avatar = None
    if title:
        try: avatar = fetch_avatar(url+'\t'+creator+'\t')
        except Exception: pass
    signature_path = path.with_suffix('.source')
    valid_cache = path.exists() and path.stat().st_size == WIDTH*height*4
    try:
        source = fetch_png(ident, high_quality=True)
    except Exception:
        if valid_cache:
            return dict(path=str(path), width=WIDTH, height=height)
        raise
    signature = hashlib.sha256(source+(avatar or b"")+title.encode()).hexdigest()
    try:
        previous = signature_path.read_text()
    except OSError:
        previous = None
    # A 720p output can still contain an old, enlarged low-resolution source.
    # Rebuild it when the shared high-quality thumbnail changes.
    if not valid_cache or previous != signature:
        with Image.open(io.BytesIO(source)) as image:
            image = ImageOps.pad(image.convert('RGBA'), (WIDTH, HEIGHT), color=(30,30,46,255))
            # mpv expects premultiplied BGRA; flatten the rounded source border.
            background = Image.new('RGBA', image.size, (30,30,46,255))
            background.alpha_composite(image)
            if title:background = header_card(background, title, avatar)
            data = background.tobytes('raw', 'BGRA')
        temporary = path.with_suffix('.'+str(os.getpid())+'.tmp')
        temporary.write_bytes(data)
        temporary.replace(path)
        signature_temp = signature_path.with_suffix("."+str(os.getpid())+".tmp")
        signature_temp.write_text(signature)
        signature_temp.replace(signature_path)
    return dict(path=str(path), width=WIDTH, height=height)


if __name__ == '__main__':
    try:
        print(json.dumps(prepare(sys.argv[1], *(sys.argv[2:4]))))
    except Exception:
        # The text countdown still works offline or when a thumbnail is missing.
        sys.exit(1)
