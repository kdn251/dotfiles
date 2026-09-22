#!/usr/bin/env python3
"""Keep Newsboat's native refresh behind the shared boat animation.

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
import subprocess
import sys
import tempfile
import termios
import time
import tty


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


def write_all(fd, data):
    while data:
        data = data[os.write(fd, data):]


def run(args):
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
    for index, arg in enumerate(args[:-1]):
        if arg in ('-u', '--url-file'):
            urls = Path(args[index + 1])
        elif arg in ('-C', '--config-file'):
            config = Path(args[index + 1])
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
    subprocess.run([sys.executable, str(Path(__file__).with_name('newsboat-shelf.py')), 'rebuild'], check=True)
    urls_version = urls.read_bytes() if urls.exists() else b''
    original = termios.tcgetattr(0)
    renderer = Renderer()
    pid = None
    master = None
    status = None
    startup_error = b""
    with tempfile.TemporaryDirectory(prefix="newsboat-progress-") as directory:
        fifo = Path(directory) / "events"
        os.mkfifo(fifo, 0o600)
        log_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
        try:
            pid, master = pty.fork()
            if pid == 0:
                # pty.fork gives Newsboat a controlling terminal, including
                # normal browser, keyboard, and job-control behavior.
                os.execvp("newsboat", ["newsboat", "-q", "-d", str(fifo), "-l", "6", *args])

            def resize(*_):
                size = fcntl.ioctl(0, termios.TIOCGWINSZ, b"\0" * 8)
                fcntl.ioctl(master, termios.TIOCSWINSZ, size)

            def forward_signal(signum, _):
                os.kill(pid, signum)

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
            finish_at = None
            next_frame = 0.0
            frame = 0
            opening_feed = False
            shelf_return = False
            count_refresh = False
            configured = [shlex.split(row, comments=True) for row in urls_version.decode().splitlines()]
            configured = [row for row in configured if row]
            fallback = next((i for i, row in enumerate(configured)
                             if row[0].startswith('query:All New Items:')), None)
            if fallback is None:
                fallback = next((i for i, row in enumerate(configured)
                                 if not row[0].startswith('query:Shelf:')), 0)
            last_regular_feed = query_offset + fallback
            selected_feed = None
            restore_feed = None
            counting_shelf = False
            shelf_has_items = False
            with selectors.DefaultSelector() as selector:
                selector.register(log_fd, selectors.EVENT_READ, "log")
                selector.register(master, selectors.EVENT_READ, "terminal")
                selector.register(0, selectors.EVENT_READ, "input")
                running = True
                while running:
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
                                for view in ('history', 'shelf'):
                                    marker = f"ConfigContainer::set_configvalue(browser, newsboat-{view}://show) called".encode()
                                    if line.rstrip().endswith(marker):
                                        view_script = f"newsboat-{view}.py"
                                if b"View::push_itemlist: retrieved feed at position " in line:
                                    opening_feed = True
                                    if not count_refresh:
                                        restore_feed = None
                                        selected_feed = int(line.rsplit(b" ", 1)[1])
                                shelf_entry = opening_feed and b'View::prepare_query_feed: query:Shelf:' in line
                                if b"View::prepare_query_feed:" in line or b"ItemListFormAction::set_feed:" in line:
                                    opening_feed = False
                                if (not shelf_return and b"ItemListFormAction::set_feed:" in line
                                        and not line.rstrip().endswith(b"title = `Shelf'")
                                        and selected_feed is not None):
                                    last_regular_feed = selected_feed
                                if shelf_return and b"ItemListFormAction::set_feed:" in line and line.rstrip().endswith(b"title = `Shelf'"):
                                    # A populated query entered the parent's article list.
                                    # Return to its feed list after our Shelf view closes.
                                    navigation = b"q"
                                    if restore_feed is not None:
                                        navigation += f":{restore_feed + 1}\n".encode()
                                        restore_feed = None
                                    write_all(master, navigation)
                                    shelf_return = False
                                if counting_shelf:
                                    if b"RssFeed::update_items: Matcher matches!" in line:
                                        shelf_has_items = True
                                    if b"ScopeMeasure: function `RssFeed::update_items' took " in line:
                                        counting_shelf = False
                                        if not shelf_has_items:
                                            # An empty query never enters an article list,
                                            # but open still changes the feed cursor.
                                            navigation = b":\x1b"
                                            if restore_feed is not None:
                                                navigation += f":{restore_feed + 1}\n".encode()
                                            write_all(master, navigation)
                                            restore_feed = None
                                            shelf_return = False
                                if shelf_entry and count_refresh:
                                    # Populate the replacement query in memory, without
                                    # presenting Shelf or changing the selected feed.
                                    count_refresh = False
                                    counting_shelf = True
                                    shelf_has_items = False
                                    shelf_return = True
                                    shelf_entry = False
                                if shelf_entry:
                                    view_script = "newsboat-shelf.py"
                                    shelf_return = True
                                    counting_shelf = True
                                    shelf_has_items = False
                                    restore_feed = last_regular_feed
                                    selected_feed = last_regular_feed
                                if b"FeedListFormAction::prepare: doing redraw" in line:
                                    current_urls = urls.read_bytes() if urls.exists() else b''
                                    if current_urls != urls_version:
                                        urls_version = current_urls
                                        count_refresh = True
                                        restore_feed = selected_feed
                                        configured = [shlex.split(row, comments=True) for row in current_urls.decode().splitlines()]
                                        configured = [row for row in configured if row]
                                        shelf_index = query_offset + next(i for i, row in enumerate(configured) if row[0].startswith('query:Shelf:'))
                                        refresh_config = Path(directory)/'refresh-shelf'
                                        refresh_config.write_text(f'bind <F12> feedlist open "{shelf_index}"\n')
                                        write_all(master, f":exec reload-urls\n:source {refresh_config}\n".encode() + b"\x1b[24~")
                                if view_script:
                                    # Temporarily give this terminal to the native history list.
                                    termios.tcsetattr(0, termios.TCSADRAIN, original)
                                    try:
                                        subprocess.run(
                                            [sys.executable, str(Path(__file__).with_name(view_script)), "show"],
                                            check=False)
                                    finally:
                                        tty.setraw(0)
                                        write_all(1, b"\x1b[?1049h\x1b[?25l")
                                        # Dismiss the empty navigation query status before repaint.
                                        write_all(master, b":\x1b\x0c" if shelf_entry else b"\x0c")
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
                                running = False
                                break
                            # Avoid navigating invisibly while covered. Ctrl-C
                            # still reaches Newsboat to interrupt its work.
                            if not progress.active or b"\x03" in data:
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
                                    if not progress.active:
                                        write_all(1, bytes(startup_output))
                                    startup_output.clear()
                            elif not progress.active:
                                write_all(1, data)
                            if progress.active:
                                pending_terminal = (pending_terminal + data)[-8192:]
                                match = TOTAL.search(CSI.sub(b"", pending_terminal))
                                if match and not progress.finished:
                                    progress.total = int(match[1])

                    now = time.monotonic()
                    if not running:
                        break
                    if progress.finished and finish_at is None:
                        finish_at = now + 0.5
                    if finish_at is not None and now >= finish_at:
                        progress.active = False
                        progress.finished = False
                        finish_at = None
                        # Ask ncurses for a complete repaint after hiding its
                        # incremental updates; never replay stale screen data.
                        write_all(1, b"\x1b[?25h\x1b[H\x1b[2J")
                        write_all(master, b"\x0c")
                    if (startup or progress.active) and now >= next_frame:
                        label = progress.caption() if progress.active else "setting sail"
                        write_all(1, renderer.draw(frame, label))
                        frame += 1
                        next_frame = now + 0.08

            _, status = os.waitpid(pid, 0)
            pid = None
            if startup_output:
                startup_error = bytes(startup_output)
        finally:
            termios.tcsetattr(0, termios.TCSADRAIN, original)
            write_all(1, b"\x1b[0m\x1b[?1049l\x1b[?25h")
            if master is not None:
                os.close(master)
            if pid:
                try:
                    os.kill(pid, signal.SIGHUP)
                    os.waitpid(pid, 0)
                except ProcessLookupError:
                    pass
            os.close(log_fd)
            renderer.close()
    if startup_error:
        write_all(2, startup_error)
    return os.waitstatus_to_exitcode(status)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
