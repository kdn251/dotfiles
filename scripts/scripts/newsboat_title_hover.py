"""Mouse hover titles composited above Kitty's terminal cells."""
from functools import lru_cache
import io
import math
import re
import struct
import time

ENABLE = b'\x1b[?1003h\x1b[?1006h'
DISABLE = b'\x1b[?1003l\x1b[?1006l'
MOUSE = re.compile(rb'\x1b\[<(\d+);(\d+);(\d+)([Mm])')


def parse_rows(value):
    rows = []
    for line in value.splitlines():
        parts = line.split(';', 3)
        try:
            left, top, right = map(int, parts[:3])
            title = parts[3]
        except (ValueError, IndexError):
            continue
        if 0 <= left < right and top >= 0 and title:
            rows.append((left, top, right, title))
    return rows


@lru_cache(maxsize=32)
def picture(title, size):
    from PIL import Image, ImageDraw, ImageFont
    rows, cols, pw, ph = struct.unpack('HHHH', size)
    cw, ch = (pw/cols if pw and cols else 10), (ph/rows if ph and rows else 20)
    width = max(1, min(72, cols-2))
    scale = 2
    font_size = max(12, round(ch * scale * .72))
    try:
        font = ImageFont.truetype('/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf', font_size)
    except OSError:
        font = ImageFont.load_default(size=font_size)
    pad = max(8, round(cw*scale))
    pixels = round(width*cw*scale)
    lines, line = [], ''
    # Keep words together, but still wrap titles containing a very long URL.
    for word in title.split():
        candidate = (line+' '+word) if line else word
        if line and font.getlength(candidate) > pixels-2*pad:
            lines.append(line)
            line = ''
        if line:
            line += ' '
        for char in word:
            if line and font.getlength(line+char) > pixels-2*pad:
                lines.append(line)
                line = ''
            line += char
    if line:
        lines.append(line)
    line_height = font_size+6
    height = max(1, math.ceil((len(lines)*line_height+2*pad)/(ch*scale)))
    height = min(height, max(1, rows-2))
    image = Image.new('RGBA', (pixels, round(height*ch*scale)))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, image.width-3, image.height-3), radius=12,
                           fill='#1e1e2e', outline='#ffffff', width=2)
    for n, line in enumerate(lines):
        draw.text((pad, pad+n*line_height), line, font=font, fill='#cdd6f4')
    output = io.BytesIO()
    image.save(output, format='PNG')
    return output.getvalue(), width, height


class Hover:
    def __init__(self, image_id):
        self.image_id = image_id
        self.rows = []
        self.pointer = None
        self.target = None
        self.due = 0
        self.shown = None
        self.pending = b''
        self.pending_due = 0
        self.enabled = False

    def dismiss(self):
        self.pointer = self.target = None
        self.due = 0

    def update(self, value):
        rows = parse_rows(value)
        if rows != self.rows:
            self.dismiss()
            self.rows = rows

    def feed(self, data):
        """Consume SGR mouse reports, retaining every unrelated keyboard byte."""
        data = self.pending+data
        self.pending = b''
        output = bytearray()
        while data:
            match = MOUSE.match(data)
            if match:
                button, x, y = map(int, match.groups()[:3])
                point = (x-1, y-1)
                if button & 32:  # Motion, including motion with a button held.
                    if point != self.pointer:
                        self.pointer = point
                        self.target = next((row for row in self.rows if row[0] <= point[0] < row[2] and point[1] == row[1]), None)
                        self.due = time.monotonic()+.5
                else:
                    self.dismiss()
                    if button & 64 and match[4] == b'M':
                        output.extend(b'\x1b[A' if button & 1 == 0 else b'\x1b[B')
                data = data[match.end():]
            elif (b'\x1b[<'.startswith(data) or re.fullmatch(rb'\x1b\[<[0-9;]*', data)) and len(data) < 64:
                self.pending = data
                self.pending_due = time.monotonic()+.05
                break
            else:
                self.dismiss()
                output.append(data[0])
                data = data[1:]
        return bytes(output)

    def flush_input(self):
        if self.pending and time.monotonic() >= self.pending_due:
            data, self.pending = self.pending, b''
            self.dismiss()
            # Don't forward an incomplete mouse report as Newsboat shortcuts.
            return b'' if data.startswith(b'\x1b[<') else data
        return b''

    def render(self, size, repaint=False):
        from newsboat_thumbnails import delete, transmit
        output = b''
        enabled = bool(self.rows)
        if enabled != self.enabled:
            output += ENABLE if enabled else DISABLE
            self.enabled = enabled
        target = self.target if time.monotonic() >= self.due else None
        if self.shown and self.shown != (target, size):
            output += delete(self.image_id)
            self.shown = None
        if target and (not self.shown or repaint):
            png, width, height = picture(target[3], size)
            rows, cols, _, _ = struct.unpack('HHHH', size)
            left = max(0, min(target[0], cols-width))
            top = target[1]+1
            if top+height > rows-1:
                top = max(0, target[1]-height)
            if not self.shown:
                output += transmit(self.image_id, png)
            output += (f'\x1b7\x1b[{top+1};{left+1}H'
                       f'\x1b_Ga=p,i={self.image_id},p=1,c={width},r={height},z=20,q=2\x1b\\\x1b8').encode()
            self.shown = (target, size)
        return output

    def close(self):
        from newsboat_thumbnails import delete
        return DISABLE+delete(self.image_id)
