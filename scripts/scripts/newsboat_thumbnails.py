"""Shared Kitty thumbnail pane for Newsboat's video item lists.

Newsboat reserves the pane and publishes its actual selection/geometry. This
relay owns all terminal output; a background worker only fetches image bytes.
"""
from collections import OrderedDict
import base64
import fcntl
import io
import json
import os
from pathlib import Path
import pty
import queue
import re
import select
import signal
import struct
import subprocess
import termios
import threading
import time
from functools import lru_cache
import tty
from urllib.request import Request, urlopen
from urllib.parse import urlparse, parse_qs

from newsboat_youtube_playlists import LIBRARY
from newsboat_media import identity
from newsboat_loading import ship_art

MARKER = b'\x1b]777;newsboat-thumbnail;'


def kitty_command(command, payload):
    return b'\x1bP@kitty-cmd'+json.dumps(dict(cmd=command,version=[0,48,2],no_response=True,payload=payload)).encode()+b'\x1b\\'


def background_opacity(env):
    # Follow Hyprland's configured transparency rather than hardcoding a new look.
    try:
        result = subprocess.run(['hyprctl','-j','getoption','decoration:active_opacity'],
                                capture_output=True,text=True,timeout=1,check=True)
        return max(0.0,min(1.0,float(json.loads(result.stdout)['float'])))
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):
        return .75


def opacity_command(env, opacity, toggle=False):
    return kitty_command('set-background-opacity',dict(opacity=opacity,
        match_window='id:'+env['KITTY_WINDOW_ID'],toggle=toggle))


def supported(env):
    return bool(env.get('KITTY_WINDOW_ID')) and not env.get('TMUX') and not env.get('STY')


class Decoder:
    def __init__(self):
        self.pending = b''

    def feed(self, data):
        data = self.pending + data
        self.pending = b''
        while data:
            start = data.find(MARKER)
            if start < 0:
                # Keep only a possible split marker, never delay ordinary text.
                keep = next((n for n in range(min(len(data), len(MARKER)-1), 0, -1)
                             if data.endswith(MARKER[:n])), 0)
                if len(data) > keep:
                    yield 'screen', data[:len(data)-keep]
                self.pending = data[len(data)-keep:] if keep else b''
                return
            if start:
                yield 'screen', data[:start]
            end = data.find(b'\x07', start+len(MARKER))
            if end < 0:
                self.pending = data[start:]
                return
            yield 'selection', data[start+len(MARKER):end].decode(errors='replace')
            data = data[end+1:]


def video_key(url):
    key = identity(url)
    if key:
        return key[1] if key[0] == 'youtube' else ':'.join(key)
    parsed = urlparse(url)
    if parsed.scheme == 'newsboat-playthroughs' and re.fullmatch(r'[A-Za-z0-9_-]+', parsed.netloc):
        return 'playlist:'+parsed.netloc
    if parsed.hostname in {'youtube.com','www.youtube.com','m.youtube.com'} and parsed.path == '/playlist':
        ident = parse_qs(parsed.query).get('list',[''])[0]
        if re.fullmatch(r'[A-Za-z0-9_-]+',ident):
            return 'playlist:'+ident
    if parsed.hostname in {'twitch.tv','www.twitch.tv'} and re.fullmatch(r'/[A-Za-z0-9_]+/?',parsed.path):
        return 'twitch-live:'+parsed.path.strip('/').lower()
    return None


def selection(value):
    match = re.fullmatch(r'(\d+);(\d+);(\d+);(\d+);(.+)', value)
    if not match:
        return None
    x, y, w, h = map(int, match.groups()[:4])
    if w < 10 or h < 4:
        return None
    key = video_key(match[5])
    return (x, y, w, h, key) if key else None


def frame_thumbnail(data):
    """Match the loader's rounded white frame without altering cached originals."""
    from PIL import Image, ImageDraw
    with Image.open(io.BytesIO(data)) as source:
        height=max(1,round(680*source.height/source.width))
        picture=source.convert('RGBA').resize((680,height),Image.Resampling.LANCZOS)
    mask=Image.new('L',picture.size,0)
    ImageDraw.Draw(mask).rounded_rectangle((2,2,677,height-3),radius=20,fill=255)
    picture.putalpha(mask)
    ImageDraw.Draw(picture).rounded_rectangle((2,2,677,height-3),radius=20,outline='#ffffff',width=4)
    output=io.BytesIO();picture.save(output,format='PNG')
    return output.getvalue()


def fetch_png(ident):
    from PIL import Image
    directory = LIBRARY/'thumbnails'
    path = directory/(ident+'.png')
    try:
        return frame_thumbnail(path.read_bytes())
    except FileNotFoundError:
        pass
    if ident.startswith('playlist:'):
        playlist_id = ident.split(':',1)[1]
        try:
            thumbnail = json.loads((LIBRARY/'playlist-covers'/(playlist_id+'.json')).read_text())['url']
        except FileNotFoundError:
            # Older saved playlists may predate cover metadata. Use their first
            # episode's thumbnail, including its cached copy when offline.
            group = json.loads((LIBRARY/'playthroughs'/(playlist_id+'.json')).read_text())
            first = next((video_key(row['url']) for row in group.get('rows', [])
                          if identity(row.get('url', ''))), None)
            if not first:
                raise ValueError('No playlist cover available')
            return fetch_png(first)
        if urlparse(thumbnail).scheme not in {'https','http'}:
            raise ValueError('No playlist cover available')
    elif ':' in ident:
        kind, value = ident.split(':',1)
        url = ('https://www.twitch.tv/videos/'+value if kind == 'twitch' else
               'https://clips.twitch.tv/'+value if kind == 'twitch-clip' else
               'https://www.twitch.tv/'+value)
        executable = Path.home()/'.local/bin/yt-dlp'
        result = subprocess.run([str(executable) if executable.exists() else 'yt-dlp',
            '--ignore-config','--skip-download','--no-playlist','--socket-timeout','4',
            '--retries','0','--print','%(thumbnail)s','--',url],
            capture_output=True,text=True,timeout=12,check=True)
        thumbnail = result.stdout.strip().splitlines()[-1]
        if urlparse(thumbnail).scheme not in {'https','http'}:
            raise ValueError('No thumbnail available')
    else:
        thumbnail = 'https://i.ytimg.com/vi/'+ident+'/mqdefault.jpg'
    request = Request(thumbnail,
                      headers={'User-Agent': 'Newsboat thumbnail preview'})
    with urlopen(request, timeout=5) as response:
        data = response.read(2*1024*1024)
    with Image.open(io.BytesIO(data)) as source:
        source.thumbnail((640, 360))
        output = io.BytesIO()
        source.convert('RGB').save(output, 'PNG')
    data = output.getvalue()
    directory.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.'+str(os.getpid())+'.tmp')
    temp.write_bytes(data)
    temp.replace(path)
    return frame_thumbnail(data)


class Fetcher:
    def __init__(self):
        self.jobs = queue.Queue(maxsize=1)
        self.results = queue.Queue()
        threading.Thread(target=self.run, daemon=True).start()

    def submit(self, ident):
        try:
            self.jobs.get_nowait()
        except queue.Empty:
            pass
        self.jobs.put_nowait(ident)

    def run(self):
        while True:
            ident = self.jobs.get()
            try:
                data = fetch_png(ident)
            except Exception:
                data = None  # Missing thumbnails must never break navigation.
            self.results.put((ident, data))


@lru_cache(maxsize=97)
def loading_png(frame, failed=False, caption=None):
    """Render the refresh ship inside the existing image placement, not curses."""
    from PIL import Image, ImageDraw, ImageFont
    caption = caption or ('Thumbnail unavailable' if failed else 'Loading thumbnail…')
    lines = caption.splitlines()
    height = 400 + 40*(len(lines)-1)
    canvas = Image.new('RGBA', (680, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    font_path = '/usr/share/fonts/TTF/JetBrainsMonoNerdFontMono-Regular.ttf'
    try:
        font = ImageFont.truetype(font_path, 28)
    except OSError:
        font = ImageFont.load_default(size=28)
    colors = {244:'#808080',203:'#ff5f5f',255:'#eeeeee',38:'#00afd7'}
    draw.rounded_rectangle((2,2,677,height-3),radius=20,fill='#1e1e2e',outline='#ffffff',width=4)
    for row,(color,line) in enumerate(ship_art(frame, 34)):
        draw.text((340,40+row*40),line,font=font,fill=colors[color],anchor='mt')
    for i,line in enumerate(lines):
        draw.text((340,330+40*i),line,font=font,fill='#cdd6f4',anchor='mt')
    output = io.BytesIO()
    canvas.save(output,format='PNG')
    return output.getvalue()


def delete(image_id):
    return f'\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\'.encode()


def transmit(image_id, png):
    encoded = base64.b64encode(png)
    packets = []
    for start in range(0, len(encoded), 4096):
        chunk = encoded[start:start+4096]
        more = int(start+4096 < len(encoded))
        header = f'a=t,f=100,i={image_id},q=2,m={more}' if start == 0 else f'm={more}'
        packets.append(b'\x1b_G'+header.encode()+b';'+chunk+b'\x1b\\')
    return b''.join(packets)


def placement(image_id, selected, size, png, loading=False):
    # Reserve a cell on each edge and retain the thumbnail's aspect ratio.
    from PIL import Image
    rows, cols, pixel_w, pixel_h = struct.unpack('HHHH', size)
    cell_w = pixel_w/cols if pixel_w and cols else 10
    cell_h = pixel_h/rows if pixel_h and rows else 20
    x, y, w, h, _ = selected
    with Image.open(io.BytesIO(png)) as image:
        iw, ih = image.size
    width = w-4
    height = max(1, min(h-3, round(width*cell_w*ih/iw/cell_h)))
    width = max(1, min(width, round(height*cell_h*iw/ih/cell_w)))
    left = x+(w-width)//2
    top = y+1
    # Graphics cover the highlight inside the rounded frame, without changing
    # any terminal cells underneath or cutting the selected row at the edges.
    clear = ''
    return (f'\x1b7{clear}\x1b[{top+1};{left+1}H'
            f'\x1b_Ga=p,i={image_id},p=1,c={width},r={height},z={1 if loading else -1},q=2\x1b\\\x1b8').encode()


def write(fd, data):
    while data:
        data = data[os.write(fd, data):]


def run(command, env):
    if env.get('NEWSBOAT_THUMBNAIL_OWNER'):
        # A single outer relay renders the current view. Nested playlist helpers
        # must not reserve a second graphics owner or change terminal opacity.
        return subprocess.call(command,env=dict(env,NEWSBOAT_THUMBNAILS='1'))
    if not supported(env):
        return subprocess.call(command, env=env)
    original = termios.tcgetattr(0)
    size = fcntl.ioctl(1, termios.TIOCGWINSZ, bytes(8))
    child_env = dict(env, NEWSBOAT_THUMBNAILS='1',NEWSBOAT_THUMBNAIL_OWNER='1')
    opacity = background_opacity(env)
    previous_opacity = env.get('NEWSBOAT_PREVIEW_OPACITY')
    child_env['NEWSBOAT_PREVIEW_OPACITY'] = str(opacity)
    pid, master = pty.fork()
    if pid == 0:
        fcntl.ioctl(0, termios.TIOCSWINSZ, size)
        os.execvpe(command[0], command, child_env)
    fcntl.ioctl(master, termios.TIOCSWINSZ, size)
    image_id = 0x40000000+os.getpid()
    decoder = Decoder()
    worker = Fetcher()
    current = None
    png = None
    images = OrderedDict()
    status = None
    previous_term = signal.getsignal(signal.SIGTERM)
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    previous_winch = signal.getsignal(signal.SIGWINCH)
    resized = False
    def resize(*_):
        nonlocal resized
        resized = True
    signal.signal(signal.SIGWINCH, resize)
    last_placeholder = None
    loader_due = 0.0
    preview_active = False
    configured = False
    def preview_mode(active):
        nonlocal preview_active, configured
        if active == preview_active:
            return
        if active:
            setup = kitty_command('load-config',{}) if not configured else b''
            write(1, setup+opacity_command(env,opacity)+
                  b'\x1b[22;0t\x1b]2;Newsboat Playlist Preview\x07')
            configured = True
        else:
            restore = opacity_command(env,float(previous_opacity)) if previous_opacity else opacity_command(env,opacity,toggle=True)
            write(1,b'\x1b[23;0t'+restore)
        preview_active = active
    try:
        tty.setraw(0)
        # Keep one compositing mode for the whole session. Switching between
        # compositor opacity and Kitty background opacity on each row changes
        # the apparent background brightness even with the same numeric alpha.
        preview_mode(True)
        while True:
            if resized:
                size = fcntl.ioctl(1, termios.TIOCGWINSZ, bytes(8))
                fcntl.ioctl(master, termios.TIOCSWINSZ, size)
                write(1, delete(image_id))
                current = png = None
                last_placeholder = None
                resized = False
            ready, _, _ = select.select([0, master], [], [], .05)
            repaint = False
            if 0 in ready:
                data = os.read(0, 65536)
                if not data:
                    break
                write(master, data)
            if master in ready:
                try:
                    data = os.read(master, 65536)
                except OSError:
                    break
                if not data:
                    break
                for kind, value in decoder.feed(data):
                    if kind == 'screen':
                        if b'\x1b[2J' in value or b'\x1b[?1049' in value:
                            write(1, delete(image_id))
                            current = png = None
                            last_placeholder = None
                        write(1, value)
                        repaint = True
                    else:
                        selected = selection(value)
                        if selected != current:
                            write(1, delete(image_id))
                            current, png = selected, None
                            loader_due = time.monotonic() + 0.5
                            last_placeholder = None
                            if current:
                                if current[4] in images:
                                    png = images[current[4]]
                                    if png:
                                        write(1, transmit(image_id, png))
                                else:
                                    worker.submit(current[4])
                            repaint = True
                # No marker escapes or terminal replies are sent to Newsboat.
            while not worker.results.empty():
                ident, data = worker.results.get_nowait()
                images[ident] = data
                while len(images) > 32:
                    images.popitem(last=False)
                if current and current[4] == ident:
                    png = data
                    if png:
                        write(1, transmit(image_id, png))
                        repaint = True
            display_png = png
            if current and not png and time.monotonic() >= loader_due:
                failed = current[4] in images
                frame = 0 if failed else int(time.monotonic() * 10) % 96
                placeholder = (frame, failed)
                display_png = loading_png(*placeholder)
                if placeholder != last_placeholder:
                    write(1, transmit(image_id, display_png))
                    last_placeholder = placeholder
                    repaint = True
            if repaint and current and display_png:
                write(1, placement(image_id, current, size, display_png, loading=not bool(png)))
            done, exit_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = exit_status
                break
        return os.waitstatus_to_exitcode(status) if status is not None else 0
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGWINCH, previous_winch)
        try:
            write(1, delete(image_id))
            preview_mode(False)
            termios.tcsetattr(0, termios.TCSANOW, original)
        except (OSError, termios.error):
            pass  # The enclosing terminal may already have closed.
        os.close(master)
        try:
            os.killpg(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except ProcessLookupError:
            pass
        except ChildProcessError:
            pass
