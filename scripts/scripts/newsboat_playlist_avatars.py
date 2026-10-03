"""Creator pictures anchored to visible list rows by the native UI."""
import io
import json
from pathlib import Path
import queue
import re
import struct
import subprocess
import threading
from functools import lru_cache

from newsboat_youtube_playlists import LIBRARY


def parse_rows(value):
    rows = []
    for line in value.splitlines():
        match = re.fullmatch(r'(\d+);(\d+);(.+)', line)
        if match:
            request = match[3]
            legacy = re.fullmatch(r'newsboat-playthroughs://([A-Za-z0-9_-]+)', request)
            if legacy:
                request = legacy[1]
            elif not request.startswith(('https://','http://','newsboat-playthroughs://','newsboat-feed://')):
                continue
            rows.append((int(match[1]), int(match[2]), request))
    return rows


def fetch_avatar(playlist_id):
    """Use existing channel metadata and notification avatar cache, never list YouTube."""
    if '://' in playlist_id:
        from newsboat_creator_images import fetch
        return fetch(playlist_id)
    group = json.loads((LIBRARY/'playthroughs'/(playlist_id+'.json')).read_text())
    channel = next((r.get('channel_id') for r in group.get('rows', [])
                    if re.fullmatch(r'UC[A-Za-z0-9_-]{22}', r.get('channel_id') or '')), None)
    if not channel:
        return None
    cached = Path.home()/'.cache/yt-channel-avatars'/(channel+'.png')
    if not cached.is_file():
        subprocess.run([str(Path(__file__).with_name('yt-channel-pic.sh')), channel],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       timeout=20, check=True)
    return cached.read_bytes()


@lru_cache(maxsize=128)
def fit_avatar(data, size):
    """A square inside two cells, with a tiny transparent margin for the highlight."""
    from PIL import Image, ImageOps
    rows, cols, pw, ph = struct.unpack('HHHH', size)
    width = max(2, round(2 * pw / cols)) if pw and cols else 20
    height = max(2, round(ph / rows)) if ph and rows else 20
    side = max(1, min(width, height)-2)
    with Image.open(io.BytesIO(data)) as source:
        picture = ImageOps.fit(source.convert('RGBA'), (side, side), method=Image.Resampling.LANCZOS)
    canvas = Image.new('RGBA', (width, height))
    canvas.paste(picture, ((width-side)//2, (height-side)//2))
    output = io.BytesIO();canvas.save(output, 'PNG')
    return output.getvalue()


class Avatars:
    def __init__(self, first_image_id):
        self.first_image_id = first_image_id
        self.rows = []
        self.images = {}
        self.requested = set()
        self.displayed = {}
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self.started = False
        self.wanted = set()

    def worker(self):
        while True:
            ident = self.jobs.get()
            if ident not in self.wanted:
                self.requested.discard(ident)
                continue
            try:
                image = fetch_avatar(ident)
            except Exception:
                image = None  # Offline/missing creators must never block the list.
            self.results.put((ident, image))

    def update(self, value):
        self.rows = parse_rows(value)
        self.wanted = {ident for _, _, ident in self.rows}
        if self.rows and not self.started:
            for _ in range(2):
                threading.Thread(target=self.worker, daemon=True).start()
            self.started = True
        for _, _, ident in self.rows:
            if ident not in self.requested:
                self.requested.add(ident)
                self.jobs.put(ident)

    def clear(self):
        from newsboat_thumbnails import delete
        output = b''.join(delete(self.first_image_id+slot) for slot in self.displayed)
        self.displayed.clear()
        self.rows = []
        return output

    def render(self, size, repaint=False):
        from newsboat_thumbnails import delete, transmit
        changed = False
        while not self.results.empty():
            ident, image = self.results.get_nowait()
            self.images[ident] = image
            while len(self.images) > 256:
                expired = next((key for key in self.images if key not in self.wanted), None)
                if expired is None:
                    break
                del self.images[expired]
                self.requested.discard(expired)
            changed = True
        desired = {slot: (x, y, ident, size) for slot, (x, y, ident) in enumerate(self.rows)
                   if self.images.get(ident)}
        if not repaint and not changed and desired == self.displayed:
            return b''
        output = []
        for slot, previous in self.displayed.items():
            if desired.get(slot) != previous:
                output.append(delete(self.first_image_id+slot))
        for slot, row in desired.items():
            x, y, ident, _ = row
            image_id = self.first_image_id+slot
            if self.displayed.get(slot) != row:
                try:
                    png = fit_avatar(self.images[ident], size)
                except Exception:
                    self.images[ident] = None
                    continue
                output.append(transmit(image_id, png))
            output.append((f'\x1b7\x1b[{y+1};{x+1}H'
                           f'\x1b_Ga=p,i={image_id},p=1,c=2,r=1,z=1,q=2\x1b\\\x1b8').encode())
        self.displayed = desired
        return b''.join(output)
