#!/usr/bin/env python3
"""Show startup and nonblocking refresh ship animations around Newsboat.

Newsboat 2.44 emits a ScopeMeasure event after each feed reload, and after the
whole batch. Consume these from a private FIFO, never a persistent debug log.
The native (started/total) status supplies only the denominator; completed
ScopeMeasure events supply the numerator, even with concurrent downloads.
"""

import errno
import fcntl
import gettext
import os
from pathlib import Path
import pty
import re
import selectors
import shlex
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time
import tty
from newsboat_random_prompt import Prompt


SLIDE_DURATION = 0.5


def slide_offset(elapsed, width, exiting=False):
    fraction = max(0.0, min(1.0, elapsed / SLIDE_DURATION))
    eased = fraction * fraction * (3 - 2 * fraction)
    return round(width * (eased if exiting else 1 - eased))


FRAME_READY = b"\x1b]777;newsboat-frame-ready\x07"
CSI = re.compile(rb"\x1b\[[0-?]*[ -/]*[@-~]")
# Match the localized loading status, not unrelated (unread/total) counts.
loading_text = gettext.translation("newsboat", fallback=True).gettext("%sLoading %s...")
loading_prefix = loading_text.split("%s")[1].encode()
TOTAL = re.compile(rb"\(\d+/(\d+)\) " + re.escape(loading_prefix))
RELOAD_START = b"Reloader::partition_reload_to_threads: starting with reload..."
FEED_DONE = b"ScopeMeasure: function `Reloader::reload' took "
BATCH_DONE = (
    b"ScopeMeasure: function `Reloader::reload_all' took ",
    b"ScopeMeasure: function `Reloader::reload_indexes' took ",
)


class Progress:
    def __init__(self):
        self.active = False
        self.finished = False
        self.completed = 0
        self.queries = 0
        self.errors = 0
        self.total = None
        self.started_at = 0.0
        self.displayed = 0
        self.new_items = 0
        self.updated_sources = set()

    def log(self, line):
        if RELOAD_START in line:
            self.__init__()
            if b" total feeds: " in line:
                self.total = int(line.rsplit(b": ", 1)[1])
            self.active = True
            self.started_at = time.monotonic()
        elif self.active:
            if b"Newsboat refresh new item source: " in line:
                self.new_items += 1
                self.updated_sources.add(line.split(b"Newsboat refresh new item source: ", 1)[1])
            elif FEED_DONE in line:
                self.completed += 1
            elif b"Reloader::reload: skipping query feed" in line:
                self.queries += 1
            elif b"USERERROR:" in line:
                self.errors += 1
            elif any(marker in line for marker in BATCH_DONE):
                self.finished = True
                # Every reload (including local query feeds) has returned.
                self.total = self.completed

    def caption(self):
        done = self.completed if self.finished else max(0, self.completed - self.queries)
        total = str(self.total) if self.total is not None else "?"
        if self.total is not None:
            done = min(done, self.total)
        # A query skip and its scope completion can arrive in different reads.
        self.displayed = max(self.displayed, done)
        word = "checked" if self.errors else "refreshed"
        result = f"{self.displayed}/{total} feeds {word}"
        if self.errors:
            result += f" ({self.errors} failed)"
        return result


    def toast_caption(self):
        caption = self.caption()
        if self.finished:
            sources = len(self.updated_sources)
            word = "source" if sources == 1 else "sources"
            caption += f"\n{self.new_items} new · {sources} {word} updated"
        return caption


class Renderer:
    def __init__(self):
        launcher = Path(__file__).with_name("newsboat-launch.sh")
        self.process = subprocess.Popen(
            ["bash", str(launcher), "--render"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        )

    def draw(self, frame, caption):
        cols, rows = os.get_terminal_size(1)
        # Small windows cannot fit the boat; keep the counter usable instead.
        if cols < 28 or rows < 20:
            return ("\x1b[?25l\x1b[H\x1b[2J" + caption[:cols - 1]).encode()
        self.process.stdin.write(f"{frame}\t{caption}\t{cols}\t{rows}\n".encode())
        self.process.stdin.flush()
        data = bytearray(b"\x1b[?25l")
        while True:
            char = self.process.stdout.read(1)
            if char == b"\0":
                return bytes(data).replace(b"\n", b"\r\n")
            if not char:
                raise RuntimeError("Boat renderer exited unexpectedly")
            data.extend(char)

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=2)
        self.process.stdout.close()

    @staticmethod
    def compact(frame, caption, cols, rows, height, offset=0):
        """Paint a small top-right toast, preserving Newsboat's cursor."""
        width = max(1, min(34, cols - 2))
        if height == 1:
            lines = ['🚢  ' + caption.splitlines()[-1][:max(0, width-4)]]
        else:
            smoke = [list(' ' * 18) for _ in range(2)]
            for stack in (7, 11):
                for puff_offset in (0, 6):
                    age = (frame // 2 + puff_offset + (2 if stack == 11 else 0)) % 12
                    smoke[1-age//6][stack+age//4] = 'o' if 3 <= age < 9 else '.'
            art = [''.join(line) for line in smoke] + [
                '      |#| |#|     ',
                '   ___|[]_[]|___  ',
                '   \\_o_o_o_o__/   ',
            ]
            colors = [244,244,203,255,203]
            if 6 <= frame % 32 < 22:
                art = art[1:] + [' ' * 18]
                colors = colors[1:] + [244]
            wave = '~^~~-~~^~~-~~^~~-~~^~~-~~'
            shift = (frame//2) % 6
            art.append(wave[shift:shift+18])
            colors.append(38)
            inner = width - 2
            art = [line.center(inner) for line in art[:-1]] + [(wave * 3)[shift:shift+inner]]
            lines = [f'│\x1b[38;5;{color}m{line}\x1b[0m│' for color,line in zip(colors,art)]
            lines.extend('│' + line[:inner].center(inner) + '│' for line in caption.splitlines())
            lines = ['╭' + '─' * inner + '╮'] + lines + ['╰' + '─' * inner + '╯']
        visible = max(0, width-offset)
        if not visible:
            return b''
        output = bytearray(b'\x1b7')
        for index,line in enumerate(lines):
            # Clip the moving toast at the right margin without wrapping ANSI
            # colors or border characters onto the next terminal row.
            clipped = []
            remaining = visible
            for part in re.split(r'(\x1b\[[0-?]*[ -/]*[@-~])', line):
                if part.startswith('\x1b'):
                    clipped.append(part)
                elif remaining:
                    clipped.append(part[:remaining])
                    remaining -= len(part[:remaining])
            output.extend(f'\x1b[{min(2, rows)+index};{max(1, cols-width-1+offset)}H\x1b[0m\x1b[{visible}X'.encode())
            output.extend(''.join(clipped).encode())
        output.extend(b'\x1b[0m\x1b8')
        return bytes(output)


def write_all(fd, data):
    while data:
        data = data[os.write(fd, data):]



def nested_view_environment(directory):
    """Nested views share the wrapper's alternate screen instead of leaving it."""
    env = os.environ.copy()
    term = env.get('TERM', 'xterm-256color')
    result = subprocess.run(['infocmp', '-1', term], capture_output=True, text=True, check=True)
    description = re.sub(r'^\s*(?:smcup|rmcup)=.*\n', '', result.stdout, flags=re.MULTILINE)
    terminfo = Path(directory)/'terminfo'
    terminfo.mkdir(exist_ok=True)
    source = Path(directory)/'nested.terminfo'
    source.write_text(description)
    subprocess.run(['tic', '-x', '-o', str(terminfo), str(source)], check=True, capture_output=True)
    env['TERMINFO'] = str(terminfo)
    return env


def run(args):
    # Use the local build for collection features. Let scrolloff center lists;
    # saved views inherit the executable path without the legacy paging override.
    paged_binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
    live_queries = paged_binary.is_file()
    if live_queries:
        os.environ['PATH'] = str(paged_binary.parent) + os.pathsep + os.environ.get('PATH', '')
        os.environ.pop('NEWSBOAT_PAGE_SCROLL', None)
        last_opened = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/last-opened'
        last_opened.parent.mkdir(parents=True, exist_ok=True)
        os.environ['NEWSBOAT_LAST_OPENED'] = str(last_opened)
        os.environ['NEWSBOAT_NOTES_STATUS'] = str(last_opened.parent/'noted-urls.txt')
        subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-notes.py')), '--refresh'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        os.environ['NEWSBOAT_DOWNLOAD_STATUS'] = str(Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/download-status.tsv')
        os.environ['NEWSBOAT_STARRED_STATUS'] = str(Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat/starred-urls.txt')
    # Preserve CLI/debug modes, which do not run the interactive feed list.
    passthrough = {"-h", "--help", "-v", "-vv", "--version", "-x", "--execute",
                   "-e", "--export-to-opml", "-i", "--import-from-opml",
                   "-d", "--log-file", "-l", "--log-level", "-X", "--vacuum",
                   "-E", "--export-to-file", "-I", "--import-from-file",
                   "--export-to-opml2", "--cleanup"}
    if not os.isatty(0) or not os.isatty(1) or any(
        arg.split("=", 1)[0] in passthrough for arg in args
    ):
        os.execvp("newsboat", ["newsboat", *args])

    urls = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home()/'.newsboat/urls'))
    config = Path.home()/'.newsboat/config'
    cache = Path.home()/'.newsboat/cache.db'
    for index, arg in enumerate(args[:-1]):
        if arg in ('-u', '--url-file'):
            urls = Path(args[index + 1])
        elif arg in ('-C', '--config-file'):
            config = Path(args[index + 1])
        elif arg in ('-c', '--cache-file'):
            cache = Path(args[index + 1])
    settings = {}
    if config.exists():
        for row in config.read_text().splitlines():
            tokens = shlex.split(row, comments=True)
            if len(tokens) == 2 and tokens[0] in {'urls-source', 'miniflux-show-special-feeds'}:
                settings[tokens[0]] = tokens[1]
    # Miniflux inserts its Starred list before locally configured queries.
    query_offset = int(settings.get('urls-source') == 'miniflux'
                       and settings.get('miniflux-show-special-feeds', 'yes') == 'yes')
    os.environ['NEWSBOAT_URLS_FILE'] = str(urls)
    remote = settings.get('urls-source') == 'miniflux'
    if remote:
        subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-commentary.py')), 'rebuild'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-favorites.py')), 'rebuild'], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen([sys.executable, str(Path(__file__).with_name('newsboat-vods.py')), 'rebuild'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen([sys.executable, str(Path(__file__).with_name('newsboat-books.py')), 'rebuild'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    startup_deadline = time.monotonic() + 5
    if remote:
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-starred.py')), 'rebuild'],
                                    check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                                    env=dict(os.environ, NEWSBOAT_QUIET_ERROR='1'))
            offline = result.returncode != 0
        except subprocess.TimeoutExpired:
            offline = True
        if offline:
            from newsboat_offline import show
            return show(config.resolve(), urls.resolve(), cache.resolve())
    urls_version = urls.read_bytes() if urls.exists() else b''
    original = termios.tcgetattr(0)
    renderer = Renderer()
    pid = None
    master = None
    nested_pid = None
    nested_master = None
    vod_monitor = None
    status = None
    startup_error = b""
    offline_requested = False
    toast_rows = 0
    previous_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGWINCH, signal.SIGTERM, signal.SIGHUP)}
    with tempfile.TemporaryDirectory(prefix="newsboat-progress-") as directory:
        os.environ['NEWSBOAT_UNDO_FILE'] = str(Path(directory)/'undo')
        os.environ['NEWSBOAT_DOWNLOAD_UNDO_HELPER'] = str(Path(__file__).with_name('newsboat_media.py'))
        if live_queries:
            os.environ['NEWSBOAT_UNDO_HELPER'] = str(Path(__file__).with_name('newsboat-starred.py'))
            os.environ['NEWSBOAT_COMMENTARY_HELPER'] = str(Path(__file__).with_name('newsboat-commentary.py'))
            os.environ['NEWSBOAT_FAVORITES_HELPER'] = str(Path(__file__).with_name('newsboat-favorites.py'))
        random_directory = Path(directory)/"random-prompt"
        random_directory.mkdir(mode=0o700)
        os.environ['NEWSBOAT_RANDOM_PROMPT_DIR'] = str(random_directory)
        random_prompt = Prompt(random_directory)
        refresh_request = Path(directory)/"refresh-request"
        os.environ["NEWSBOAT_REFRESH_REQUEST"] = str(refresh_request)
        view_env = nested_view_environment(directory)
        if live_queries:
            view_env["NEWSBOAT_SYNC_VIEW"] = "1"
        fifo = Path(directory) / "events"
        os.mkfifo(fifo, 0o600)
        log_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        try:
            pid, master = pty.fork()
            if pid == 0:
                if live_queries:
                    os.environ["NEWSBOAT_LIVE_QUERIES"] = str(urls)
                    os.environ["NEWSBOAT_NESTED_VIEWS"] = "1"
                # pty.fork gives Newsboat a controlling terminal, including
                # normal browser, keyboard, and job-control behavior.
                os.execvp("newsboat", ["newsboat", "-q", "-d", str(fifo), "-l", "6", *args])

            def resize(*_):
                size = fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8)
                height, width, xpixels, ypixels = struct.unpack('HHHH', size)
                height, width = height or 24, width or 80
                size = struct.pack('HHHH', height, width, xpixels, ypixels)
                fcntl.ioctl(master, termios.TIOCSWINSZ, size)
                if nested_master is not None:
                    fcntl.ioctl(nested_master, termios.TIOCSWINSZ, size)

            def forward_signal(signum, _):
                # Avoid Newsboat's terminal-reset SIGHUP handler after the
                # terminal disappears: it can deadlock inside STFL.
                try:
                    os.kill(pid, signal.SIGTERM if signum == signal.SIGHUP else signum)
                except ProcessLookupError:
                    pass

            resize()
            signal.signal(signal.SIGWINCH, resize)
            signal.signal(signal.SIGTERM, forward_signal)
            signal.signal(signal.SIGHUP, forward_signal)
            vod_monitor = subprocess.Popen([sys.executable, str(Path(__file__).with_name('newsboat_vod_progress.py')), str(os.getpid())],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            tty.setraw(0)
            write_all(1, b"\x1b[?1049h\x1b[?25l")
            progress = Progress()
            startup = True
            pending_log = b""
            pending_terminal = b""
            startup_output = bytearray()
            return_output = bytearray()
            return_deadline = None
            finish_at = None
            next_frame = 0.0
            frame = 0
            toast_offset = 0
            toast_started = None
            animation_started = time.monotonic()
            def paint_terminal(data):
                # ncurses can redraw the area behind the toast. Restore the current frame in the same terminal
                # update rather than leaving it blank until the next tick.
                if toast_rows:
                    cols, rows = os.get_terminal_size(1)
                    data = data.replace(b"\x1b[?2026h", b"").replace(b"\x1b[?2026l", b"")
                    data += renderer.compact(frame, progress.toast_caption(),
                                             cols, rows, toast_rows, toast_offset)
                    data = b"\x1b[?2026h" + data + b"\x1b[?2026l"
                if random_prompt.current:
                    cols, rows = os.get_terminal_size(1)
                    data += random_prompt.draw(cols, rows)
                write_all(1, data)

            opening_feed = False
            starred_return = False
            count_refresh = False
            configured = [shlex.split(row, comments=True) for row in urls_version.decode().splitlines()]
            configured = [row for row in configured if row]
            fallback = next((i for i, row in enumerate(configured)
                             if row[0].startswith('query:📬 New:')), None)
            if fallback is None:
                fallback = next((i for i, row in enumerate(configured)
                                 if not row[0].startswith('query:⭐ Starred:')), 0)
            last_regular_feed = query_offset + fallback
            selected_feed = None
            restore_feed = None
            counting_starred = False
            starred_has_items = False
            with selectors.DefaultSelector() as selector:
                selector.register(log_fd, selectors.EVENT_READ, "log")
                selector.register(master, selectors.EVENT_READ, "terminal")
                selector.register(0, selectors.EVENT_READ, "input")
                running = True
                while running:
                    if remote and startup and time.monotonic() >= startup_deadline:
                        offline_requested = True
                        os.kill(pid, signal.SIGTERM)
                        break
                    if not startup and random_prompt.poll():
                        cols, rows = os.get_terminal_size(1)
                        write_all(1, random_prompt.draw(cols, rows))
                    if refresh_request.exists() and not progress.active:
                        refresh_request.unlink(missing_ok=True)
                        write_all(master, b":exec reload-all\n")
                    animation_wait = max(0, next_frame-time.monotonic()) if startup or progress.active else 0.04
                    events = selector.select(min(0.04, animation_wait))
                    # Observe completion events before dealing with terminal
                    # updates from the same refresh. No raw logs are retained.
                    events.sort(key=lambda event: event[0].data != "log")
                    for key, _ in events:
                        if key.data == "log":
                            chunk = os.read(log_fd, 65536)
                            pending_log += chunk
                            while b"\n" in pending_log:
                                line, pending_log = pending_log.split(b"\n", 1)
                                # A dedicated binding signal avoids the browser operation,
                                # which refuses query feeds before launching any command.
                                view_script = None
                                for view in ('history', 'starred'):
                                    marker = f"ConfigContainer::set_configvalue(browser, newsboat-{view}://show) called".encode()
                                    if line.rstrip().endswith(marker):
                                        view_script = f"newsboat-{view}.py"
                                if b"View::push_itemlist: retrieved feed at position " in line:
                                    opening_feed = True
                                    if not count_refresh:
                                        restore_feed = None
                                        selected_feed = int(line.rsplit(b" ", 1)[1])
                                starred_entry = opening_feed and 'View::prepare_query_feed: query:⭐ Starred:'.encode() in line
                                if b"View::prepare_query_feed:" in line or b"ItemListFormAction::set_feed:" in line:
                                    opening_feed = False
                                if (not starred_return and b"ItemListFormAction::set_feed:" in line
                                        and not line.rstrip().endswith("title = `⭐ Starred'".encode())
                                        and selected_feed is not None):
                                    last_regular_feed = selected_feed
                                if starred_return and b"ItemListFormAction::set_feed:" in line and line.rstrip().endswith("title = `⭐ Starred'".encode()):
                                    # A populated query entered the parent's article list.
                                    # Return to its feed list after our Starred view closes.
                                    navigation = b"q"
                                    if restore_feed is not None:
                                        navigation += f":{restore_feed + 1}\n".encode()
                                        restore_feed = None
                                    write_all(master, navigation)
                                    starred_return = False
                                if counting_starred:
                                    if b"RssFeed::update_items: Matcher matches!" in line:
                                        starred_has_items = True
                                    if b"ScopeMeasure: function `RssFeed::update_items' took " in line:
                                        counting_starred = False
                                        if not starred_has_items:
                                            # An empty query never enters an article list,
                                            # but open still changes the feed cursor.
                                            navigation = b":\x1b"
                                            if restore_feed is not None:
                                                navigation += f":{restore_feed + 1}\n".encode()
                                            write_all(master, navigation)
                                            restore_feed = None
                                            starred_return = False
                                if starred_entry and count_refresh:
                                    # Populate the replacement query in memory, without
                                    # presenting Starred or changing the selected feed.
                                    count_refresh = False
                                    counting_starred = True
                                    starred_has_items = False
                                    starred_return = True
                                    starred_entry = False
                                if starred_entry:
                                    view_script = "newsboat-starred.py"
                                    starred_return = True
                                    counting_starred = True
                                    starred_has_items = False
                                    restore_feed = selected_feed
                                if b"FeedListFormAction::prepare: doing redraw" in line:
                                    current_urls = urls.read_bytes() if urls.exists() else b''
                                    if current_urls != urls_version and not live_queries:
                                        urls_version = current_urls
                                        count_refresh = True
                                        restore_feed = selected_feed
                                        configured = [shlex.split(row, comments=True) for row in current_urls.decode().splitlines()]
                                        configured = [row for row in configured if row]
                                        starred_index = query_offset + next(i for i, row in enumerate(configured) if row[0].startswith('query:⭐ Starred:'))
                                        refresh_config = Path(directory)/'refresh-starred'
                                        refresh_config.write_text(f'bind <F12> feedlist open "{starred_index}"\n')
                                        write_all(master, f":exec reload-urls\n:source {refresh_config}\n".encode() + b"\x1b[24~")
                                if b"FeedListFormAction: opening Starred view" in line:
                                    view_script = "newsboat-starred.py"
                                if b"FeedListFormAction: opening Commentary view" in line:
                                    view_script = "newsboat-commentary.py"
                                if b"FeedListFormAction: opening Favorites view" in line:
                                    view_script = "newsboat-favorites.py"
                                if b"FeedListFormAction: opening VODs view" in line:
                                    view_script = "newsboat-vods.py"
                                if b"FeedListFormAction: opening Books view" in line:
                                    view_script = "newsboat-books.py"
                                if view_script and not live_queries:
                                    termios.tcsetattr(0, termios.TCSADRAIN, original)
                                    try:
                                        subprocess.run([sys.executable, str(Path(__file__).with_name(view_script)), "show"],
                                                       check=False, env=view_env)
                                    finally:
                                        tty.setraw(0)
                                        return_deadline = time.monotonic() + 0.12
                                        write_all(master, b":\x1b\x0c" if starred_entry else b"\x0c")
                                    view_script = None
                                if view_script:
                                    # Keep the outer event loop alive while a saved
                                    # list owns a separate PTY. Refresh logs and the
                                    # toast continue independently of navigation.
                                    if nested_pid is None:
                                        write_all(1, b"\x1b[?2026h")
                                        nested_pid, nested_master = pty.fork()
                                        if nested_pid == 0:
                                            os.execve(sys.executable,
                                                [sys.executable, str(Path(__file__).with_name(view_script)), "show"],
                                                view_env)
                                        resize()
                                        selector.register(nested_master, selectors.EVENT_READ, "nested")
                                        nested_starred_entry = starred_entry
                                was_active = progress.active
                                progress.log(line)
                                if RELOAD_START in line:
                                    finish_at = None
                                if progress.active and (not was_active or RELOAD_START in line):
                                    frame = 0
                                    animation_started = time.monotonic()
                                    next_frame = 0
                                    pending_terminal = b""
                            # Bound unfinished diagnostic payloads, e.g. HTML.
                            pending_log = pending_log[-65536:]
                        elif key.data == "input":
                            data = os.read(0, 4096)
                            if not data:
                                try:
                                    os.kill(pid, signal.SIGTERM)
                                except ProcessLookupError:
                                    pass
                                running = False
                                break
                            if random_prompt.current:
                                if random_prompt.handle(data):
                                    write_all(nested_master if nested_master is not None else master, b"\x0c")
                                continue
                            write_all(nested_master if nested_master is not None else master, data)
                        else:
                            try:
                                data = os.read(key.fd, 65536)
                            except OSError as error:
                                if error.errno != errno.EIO:
                                    raise
                                data = b""
                            if key.data == "nested":
                                if data:
                                    paint_terminal(data.replace(FRAME_READY, b""))
                                else:
                                    selector.unregister(nested_master)
                                    os.close(nested_master)
                                    nested_master = None
                                    os.waitpid(nested_pid, 0)
                                    nested_pid = None
                                    return_deadline = time.monotonic() + 0.12
                                    write_all(master, b":\x1b\x0c" if nested_starred_entry else b"\x0c")
                                continue
                            if not data:
                                running = False
                                break
                            if startup:
                                startup_output.extend(data)
                                # ncurses entering its screen is the handoff.
                                if b"\x1b[?1049h" in startup_output or b"\x1b[?47h" in startup_output:
                                    startup = False
                                    write_all(1, bytes(startup_output))
                                    startup_output.clear()
                            elif nested_master is None:
                                if return_deadline is not None:
                                    return_output.extend(data)
                                else:
                                    paint_terminal(data.replace(FRAME_READY, b""))
                            if progress.active:
                                pending_terminal = (pending_terminal + data)[-8192:]
                                match = TOTAL.search(CSI.sub(b"", pending_terminal))
                                if match and not progress.finished:
                                    progress.total = int(match[1])

                    now = time.monotonic()
                    if not running:
                        break
                    if return_deadline is not None and (FRAME_READY in return_output or now >= return_deadline):
                        frame_output = re.sub(rb"\x1b\[\?(?:1049|1047|47)[hl]", b"", bytes(return_output).replace(FRAME_READY, b""))
                        paint_terminal(b"\x1b[?2026h" + frame_output + b"\x1b[?2026l")
                        return_output.clear()
                        return_deadline = None
                    if progress.finished and finish_at is None:
                        finish_at = now + 3.0
                    if finish_at is not None and now >= finish_at:
                        progress.active = False
                        progress.finished = False
                        finish_at = None
                    cols, rows = os.get_terminal_size(1)
                    wanted_toast = (9 + int(progress.finished) if cols >= 42 and rows >= 12 else 1) if progress.active and not startup else 0
                    if wanted_toast != toast_rows:
                        if wanted_toast and not toast_rows:
                            toast_started = now
                        toast_rows = wanted_toast
                        if not toast_rows:
                            # Restore the list underneath the dismissed toast.
                            write_all(nested_master if nested_master is not None else master, b"\x0c")
                        next_frame = 0
                    if (startup or progress.active) and now >= next_frame:
                        frame = int((now-animation_started)/0.08)
                        sliding = False
                        label = progress.toast_caption() if progress.active else "setting sail"
                        if startup:
                            write_all(1, renderer.draw(frame, label))
                        elif return_deadline is None:
                            width = max(1, min(34, cols - 2))
                            previous_offset = toast_offset
                            if toast_rows == 1:
                                toast_offset = 0
                            elif finish_at is not None and now >= finish_at - SLIDE_DURATION:
                                toast_offset = slide_offset(now-(finish_at-SLIDE_DURATION), width, exiting=True)
                                sliding = True
                            else:
                                elapsed = now-toast_started if toast_started is not None else SLIDE_DURATION
                                toast_offset = slide_offset(elapsed, width)
                                sliding = elapsed < SLIDE_DURATION
                            if toast_offset > previous_offset:
                                # Repaint the newly exposed list behind the
                                # departing toast, then composite in one update.
                                write_all(nested_master if nested_master is not None else master, b"\x0c")
                            else:
                                write_all(1, b"\x1b[?2026h" +
                                          renderer.compact(frame, label, cols, rows, toast_rows, toast_offset) +
                                          b"\x1b[?2026l")
                        if random_prompt.current:
                            write_all(1, random_prompt.draw(cols, rows))
                        next_frame = now + (1/60 if sliding else 0.08)

            _, status = os.waitpid(pid, 0)
            pid = None
            if startup_output:
                startup_error = bytes(startup_output)
        finally:
            # A closed terminal must not prevent stopping the child and
            # releasing its database lock.
            try:
                termios.tcsetattr(0, termios.TCSADRAIN, original)
                write_all(1, b"\x1b[0m\x1b[?1049l\x1b[?25h")
            except (OSError, termios.error):
                pass
            if vod_monitor is not None:
                if vod_monitor.poll() is None:
                    try:
                        os.killpg(vod_monitor.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                vod_monitor.wait(timeout=3)
            if nested_pid:
                try:
                    os.killpg(nested_pid, signal.SIGTERM)
                    os.waitpid(nested_pid, 0)
                except ProcessLookupError:
                    pass
            if nested_master is not None:
                os.close(nested_master)
            if master is not None:
                os.close(master)
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)
                except ProcessLookupError:
                    pass
            try:
                from newsboat_download_undo import cleanup
                cleanup()
            except (OSError, ValueError):
                pass
            os.close(log_fd)
            renderer.close()
            for sig, handler in previous_signals.items():
                signal.signal(sig, handler)
    if remote and startup_error and re.search(rb'connect|timed out|resolve host|network|HTTP.*(?:401|403|50[234])', startup_error, re.I):
        offline_requested = True
    if offline_requested:
        from newsboat_offline import show
        return show(config.resolve(), urls.resolve(), cache.resolve())
    if startup_error:
        write_all(2, startup_error)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
