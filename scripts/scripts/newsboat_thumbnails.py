"""Kitty thumbnail pane for the nested playlist browser.

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
import tty
from urllib.request import Request, urlopen

from newsboat_youtube_playlists import LIBRARY

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


def selection(value):
    match = re.fullmatch(r'(\d+);(\d+);(\d+);(\d+);https://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]{11})', value)
    if not match:
        return None
    x, y, w, h = map(int, match.groups()[:4])
    if w < 10 or h < 4:
        return None
    return x, y, w, h, match[5]


def fetch_png(ident):
    from PIL import Image
    directory = LIBRARY/'thumbnails'
    path = directory/(ident+'.png')
    try:
        return path.read_bytes()
    except FileNotFoundError:
        pass
    request = Request('https://i.ytimg.com/vi/'+ident+'/mqdefault.jpg',
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
    return data


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


def placement(image_id, selected, size, png):
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
    # A negative z-index lets toast text remain legible above the preview.
    return (f'\x1b7\x1b[{top+1};{left+1}H'
            f'\x1b_Ga=p,i={image_id},p=1,c={width},r={height},z=-1,q=2\x1b\\\x1b8').encode()


def write(fd, data):
    while data:
        data = data[os.write(fd, data):]


def run(command, env):
    if not supported(env):
        return subprocess.call(command, env=env)
    original = termios.tcgetattr(0)
    size = fcntl.ioctl(1, termios.TIOCGWINSZ, bytes(8))
    child_env = dict(env, NEWSBOAT_THUMBNAILS='1')
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
    try:
        tty.setraw(0)
        # Move transparency from the compositor to Kitty's background. Graphics
        # stay opaque, while the background retains its usual transparency.
        write(1, kitty_command('load-config',{})+opacity_command(env,opacity)+
              b'\x1b[22;0t\x1b]2;Newsboat Playlist Preview\x07')
        while True:
            if resized:
                size = fcntl.ioctl(1, termios.TIOCGWINSZ, bytes(8))
                fcntl.ioctl(master, termios.TIOCSWINSZ, size)
                write(1, delete(image_id))
                current = png = None
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
                        write(1, value)
                        repaint = True
                    else:
                        selected = selection(value)
                        if selected != current:
                            write(1, delete(image_id))
                            current, png = selected, None
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
            if repaint and current and png:
                write(1, placement(image_id, current, size, png))
            done, exit_status = os.waitpid(pid, os.WNOHANG)
            if done:
                status = exit_status
                break
        return os.waitstatus_to_exitcode(status) if status is not None else 0
    finally:
        signal.signal(signal.SIGTERM, previous_term)
        signal.signal(signal.SIGWINCH, previous_winch)
        try:
            restore = opacity_command(env,float(previous_opacity)) if previous_opacity else opacity_command(env,opacity,toggle=True)
            write(1, delete(image_id)+b'\x1b[23;0t'+restore)
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
