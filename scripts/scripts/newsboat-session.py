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

    def log(self, line):
        if RELOAD_START in line:
            self.__init__()
            self.active = True
            self.started_at = time.monotonic()
        elif self.active:
            if FEED_DONE in line:
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
    def compact(frame, caption, cols, rows, height):
        """Paint only the reserved footer, preserving Newsboat's cursor."""
        if height == 1:
            lines = ['🚢  ' + caption[:max(0, cols-5)]]
        else:
            smoke = [list(' ' * 18) for _ in range(2)]
            for stack in (7, 11):
                for offset in (0, 6):
                    age = (frame // 2 + offset + (2 if stack == 11 else 0)) % 12
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
            lines = [f'\x1b[38;5;{color}m{line}\x1b[0m' for color,line in zip(colors,art)]
            label = caption[:max(0,cols-23)]
            lines[-1] += '  ' + label
        output = bytearray(b'\x1b7')
        for index,line in enumerate(lines):
            output.extend(f'\x1b[{rows-height+index+1};1H\x1b[2K'.encode())
            output.extend(line.encode())
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
    # Use the optional local build for page-at-a-time list navigation. Child
    # History/Starred views inherit both the executable path and this setting.
    paged_binary = Path.home()/'.local/lib/newsboat-paged/newsboat'
    live_queries = paged_binary.is_file()
    if live_queries:
        os.environ['PATH'] = str(paged_binary.parent) + os.pathsep + os.environ.get('PATH', '')
        os.environ['NEWSBOAT_PAGE_SCROLL'] = '1'
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
    status = None
    startup_error = b""
    offline_requested = False
    footer_rows = 0
    previous_signals = {sig: signal.getsignal(sig) for sig in (signal.SIGWINCH, signal.SIGTERM, signal.SIGHUP)}
    with tempfile.TemporaryDirectory(prefix="newsboat-progress-") as directory:
        if live_queries:
            os.environ['NEWSBOAT_UNDO_FILE'] = str(Path(directory)/'undo')
            os.environ['NEWSBOAT_UNDO_HELPER'] = str(Path(__file__).with_name('newsboat-starred.py'))
            os.environ['NEWSBOAT_COMMENTARY_HELPER'] = str(Path(__file__).with_name('newsboat-commentary.py'))
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
                size = struct.pack('HHHH', max(1, height-footer_rows), width, xpixels, ypixels)
                fcntl.ioctl(master, termios.TIOCSWINSZ, size)

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
                    events = selector.select(0.04)
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
                                if view_script:
                                    # Temporarily give this terminal to the native history list.
                                    termios.tcsetattr(0, termios.TCSADRAIN, original)
                                    try:
                                        if live_queries:
                                            write_all(1, b"\x1b[?2026h")
                                        subprocess.run(
                                            [sys.executable, str(Path(__file__).with_name(view_script)), "show"],
                                            check=False, env=view_env)
                                    finally:
                                        write_all(1, b"\x1b[?2026l")
                                        tty.setraw(0)
                                        return_deadline = time.monotonic() + 0.12
                                        # Dismiss the empty navigation query status before repaint.
                                        write_all(master, b":\x1b\x0c" if starred_entry else b"\x0c")
                                was_active = progress.active
                                progress.log(line)
                                if progress.active and not was_active:
                                    frame = 0
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
                            write_all(master, data)
                        else:
                            try:
                                data = os.read(master, 65536)
                            except OSError as error:
                                if error.errno != errno.EIO:
                                    raise
                                data = b""
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
                            else:
                                if return_deadline is not None:
                                    return_output.extend(data)
                                else:
                                    write_all(1, data.replace(FRAME_READY, b""))
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
                        write_all(1, b"\x1b[?2026h" + frame_output + b"\x1b[?2026l")
                        return_output.clear()
                        return_deadline = None
                    if progress.finished and finish_at is None:
                        finish_at = now + 0.5
                    if finish_at is not None and now >= finish_at:
                        progress.active = False
                        progress.finished = False
                        finish_at = None
                    cols, rows = os.get_terminal_size(1)
                    wanted_footer = (6 if cols >= 42 and rows >= 16 else 1) if progress.active and not startup else 0
                    if wanted_footer != footer_rows:
                        footer_rows = wanted_footer
                        resize()
                        write_all(master, b"\x0c")
                        next_frame = 0
                    if (startup or progress.active) and now >= next_frame:
                        label = progress.caption() if progress.active else "setting sail"
                        if startup:
                            write_all(1, renderer.draw(frame, label))
                        elif return_deadline is None:
                            write_all(1, renderer.compact(frame, label, cols, rows, footer_rows))
                        frame += 1
                        next_frame = now + 0.08

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
            if master is not None:
                os.close(master)
            if pid:
                try:
                    os.kill(pid, signal.SIGTERM)
                    os.waitpid(pid, 0)
                except ProcessLookupError:
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
