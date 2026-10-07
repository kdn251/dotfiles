#!/usr/bin/env python3
"""Silent, non-focusing Wayland popup driven by Herdr over SSH."""
import argparse
import fcntl
import json
import logging
import os
from pathlib import Path
import queue
import select
import shlex
import signal
import socket
import subprocess
import threading
import time
import tomllib

from state import Completions, NeedsAttention, completion_label, detail_text, popup_title

BASE = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'computer-notification'
CONFIG = Path.home() / '.config/computer-notification/config.toml'
LOG = logging.getLogger('computer-notification')


def configuration():
    cfg = dict(host='boole', remote_socket='~/.config/herdr/herdr.sock', pixel_scale=5,
               duration=6.0, margin_top=48, margin_right=18)
    if CONFIG.exists():
        cfg.update(tomllib.loads(CONFIG.read_text()))
    if not isinstance(cfg['host'], str) or cfg['host'].startswith('-'):
        raise ValueError('host must be an SSH host alias')
    for key, low, high in [('pixel_scale', 2, 10), ('margin_top', 0, 1000), ('margin_right', 0, 1000)]:
        cfg[key] = max(low, min(high, int(cfg[key])))
    cfg['duration'] = max(4.0, min(15.0, float(cfg['duration'])))
    return cfg


def watcher(cfg, inbox, stop):
    code = (BASE / 'bridge.py').read_text()
    command = ['ssh', '-T', '-S', 'none', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
               '-o', 'ServerAliveInterval=10', '-o', 'ServerAliveCountMax=2',
               '-o', 'ControlMaster=no', '-o', 'ControlPersist=no', cfg['host'],
               'python3 -u -c ' + shlex.quote(code) + ' ' + shlex.quote(cfg['remote_socket'])]
    backoff = 2
    while not stop.is_set():
        proc = None
        try:
            proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=None)
            buf = b''
            last = time.monotonic()
            offset = None
            while not stop.is_set():
                if time.monotonic() - last > 25:
                    raise RuntimeError('SSH/Herdr heartbeat timed out')
                if not select.select([proc.stdout], [], [], 1)[0]:
                    continue
                data = os.read(proc.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError(f'SSH stream closed (exit {proc.poll()})')
                buf += data
                if len(buf) > 4 * 1024 * 1024:
                    raise RuntimeError('SSH buffer exceeded limit')
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    event = json.loads(line)
                    if offset is None:
                        if event.get('kind') != 'baseline':
                            raise RuntimeError('missing initial baseline')
                        offset = time.time() - event['time']
                    # Accounts for host clock offset. Discard buffered completions
                    # after sleep/network stalls rather than replaying them.
                    age = time.time() - event['time'] - offset
                    if abs(age) > 15:
                        raise RuntimeError('stale stream or clock change; re-baselining')
                    event['received'] = time.monotonic()
                    inbox.put_nowait(event)
                    last = time.monotonic()
                    backoff = 2
        except (OSError, ValueError, RuntimeError, queue.Full) as error:
            LOG.warning('%s; reconnect in %ss', error, backoff)
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                proc.stdout.close()
            # Drop all pending snapshots when connection continuity is lost.
            while True:
                try:
                    inbox.get_nowait()
                except queue.Empty:
                    break
            inbox.put_nowait({'kind': 'disconnected'})
        stop.wait(backoff)
        backoff = min(60, backoff * 2)


def daemon():
    import gi
    gi.require_version('Gtk', '3.0')
    gi.require_version('GtkLayerShell', '0.1')
    from gi.repository import Gtk, GLib, GLibUnix, GtkLayerShell, Pango
    import cairo

    cfg = configuration()
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock = (RUNTIME / 'lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('computer-notification is already running')
    if not GtkLayerShell.is_supported():
        raise SystemExit('A Wayland session with layer-shell support is required')
    control = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    endpoint = RUNTIME / 'control.sock'
    endpoint.unlink(missing_ok=True)
    control.bind(str(endpoint))
    os.chmod(endpoint, 0o600)
    control.setblocking(False)

    source = json.loads((BASE / 'frames.json').read_text())['frames']
    scale = cfg['pixel_scale']
    colors = {}
    frames = []
    for frame in source:
        cells = []
        for y, row in enumerate(frame['pixels']):
            for x, color in enumerate(row):
                if color:
                    colors.setdefault(color, tuple(int(color[i:i+2], 16) / 255 for i in (1, 3, 5)))
                    cells.append((x, y, colors[color]))
        frames.append(cells)

    win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    win.set_title('Pi computer notification')
    win.set_decorated(False)
    win.set_resizable(False)
    win.set_accept_focus(False)
    win.set_focus_on_map(False)
    win.set_app_paintable(True)
    visual = win.get_screen().get_rgba_visual()
    if visual:
        win.set_visual(visual)
    GtkLayerShell.init_for_window(win)
    GtkLayerShell.set_namespace(win, 'computer-notification')
    GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
    GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.NONE)
    GtkLayerShell.set_exclusive_zone(win, 0)
    for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.RIGHT):
        GtkLayerShell.set_anchor(win, edge, True)
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.TOP, cfg['margin_top'])
    GtkLayerShell.set_margin(win, GtkLayerShell.Edge.RIGHT, cfg['margin_right'])
    win.connect('realize', lambda w: w.get_window().input_shape_combine_region(cairo.Region(), 0, 0))

    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
    box.set_border_width(14)
    win.add(box)
    art = Gtk.DrawingArea()
    art.set_size_request(38 * scale, 26 * scale)
    box.pack_start(art, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    text.set_valign(Gtk.Align.CENTER)
    text.set_size_request(38 * scale, -1)
    box.pack_start(text, True, True, 0)
    title = Gtk.Label(label='Clanker is ready')
    title.set_xalign(0.5)
    title.set_yalign(0.5)
    title.set_name('computer-title')
    text.pack_start(title, False, False, 0)
    detail = Gtk.Label()
    detail.set_name('computer-detail')
    detail.set_xalign(0.5)
    detail.set_justify(Gtk.Justification.CENTER)
    detail.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    detail.set_max_width_chars(32)
    text.pack_start(detail, False, False, 0)
    css = Gtk.CssProvider()
    css.load_from_data(b'window { background-color: rgb(25, 30, 32); border: 1px solid #756e62; border-radius: 12px; } #computer-title { color: #eadfc4; font: bold 13px sans-serif; } #computer-detail { color: #a6b6ae; font: 11px sans-serif; }')
    Gtk.StyleContext.add_provider_for_screen(win.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def background(widget, cr):
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)
        context = widget.get_style_context()
        Gtk.render_background(context, cr, 0, 0, widget.get_allocated_width(), widget.get_allocated_height())
        Gtk.render_frame(context, cr, 0, 0, widget.get_allocated_width(), widget.get_allocated_height())
        return False

    win.connect('draw', background)
    state = {'start': 0.0, 'deadline': 0.0, 'count': 0, 'connected': False, 'panes': 0}
    detector = Completions()
    attention_detector = NeedsAttention()
    inbox = queue.Queue(maxsize=32)
    stop = threading.Event()
    thread = threading.Thread(target=watcher, args=(cfg, inbox, stop), daemon=True)

    def save_status():
        target = RUNTIME / 'status.json'
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps({'pid': os.getpid(), 'host': cfg['host'],
                                   'connected': state['connected'], 'pi_agents': state['panes']}))
        temp.replace(target)

    def show(count=1, labels=None, attention=0):
        now = time.monotonic()
        if not win.get_visible():
            state.update(start=now, deadline=now + cfg['duration'], count=0, labels=[], attention=0)
        else:
            # Coalesce, never queue an unbounded backlog or extend indefinitely.
            state['deadline'] = min(state['start'] + cfg['duration'] * 2,
                                    max(state['deadline'], now + 2))
        state['count'] = min(999, state['count'] + count)
        state['attention'] = min(999, state['attention'] + attention)
        title.set_text(popup_title(state['count'], state['attention']))
        labels = labels if labels is not None else [
            'Preview: ' + state.get('preview_label', 'project · tab name')
        ] * min(count, 2)
        state['labels'] = (state['labels'] + labels)[-2:]
        detail.set_text(detail_text(state['labels'], state['count']))
        win.show_all()  # Never present(), grab focus, or dispatch Hyprland actions.
        LOG.info('Popup: %s update(s), %s needing attention', state['count'], state['attention'])

    def draw(widget, cr):
        elapsed = (time.monotonic() - state['start']) * 6000 / cfg['duration']
        index = min(len(frames) - 1, max(0, int(elapsed / 70)))
        cr.set_antialias(cairo.ANTIALIAS_NONE)
        xoff = (widget.get_allocated_width() - 38 * scale) // 2
        for x, y, color in frames[index]:
            cr.set_source_rgb(*color)
            cr.rectangle(xoff + x * scale, y * scale, scale, scale)
            cr.fill()
        return False

    art.connect('draw', draw)

    def tick():
        # Both control requests and remote input are bounded per tick.
        previews = 0
        for _ in range(100):
            try:
                if control.recv(64) == b'preview':
                    previews += 1
            except BlockingIOError:
                break
        if previews:
            show(previews)
        for _ in range(32):
            try:
                event = inbox.get_nowait()
            except queue.Empty:
                break
            kind = event['kind']
            if kind == 'disconnected':
                state.update(connected=False, panes=0)
                detector.previous.clear()
                attention_detector.previous.clear()
                save_status()
                continue
            stale = time.monotonic() - event['received'] > 15
            baseline = kind == 'baseline' or stale or not state['connected']
            agents = event['agents']
            state['preview_label'] = completion_label(agents[0]) if agents else 'project · tab name'
            ready = detector.update(agents, baseline=baseline)
            blocked = attention_detector.update(agents, baseline=baseline)
            state.update(connected=not stale, panes=len(agents))
            if kind == 'baseline':
                LOG.info('Connected to %s: %s lifecycle-reported Pi agents; no history replay', cfg['host'], len(agents))
            save_status()
            if ready or blocked:
                labels = [completion_label(agent) for agent in ready]
                labels += [completion_label(agent) + ' · needs input' for agent in blocked]
                show(len(ready) + len(blocked), labels, attention=len(blocked))
        if win.get_visible():
            if time.monotonic() >= state['deadline']:
                win.hide()
                LOG.info('Popup dismissed')
            else:
                art.queue_draw()
        return GLib.SOURCE_CONTINUE

    def shutdown(*_):
        stop.set()
        Gtk.main_quit()
        return GLib.SOURCE_REMOVE

    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, shutdown)
    GLibUnix.signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, shutdown)
    GLib.timeout_add(70, tick)
    save_status()
    thread.start()
    try:
        Gtk.main()
    finally:
        stop.set()
        thread.join(timeout=5)
        control.close()
        endpoint.unlink(missing_ok=True)
        (RUNTIME / 'status.json').unlink(missing_ok=True)
        lock.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['daemon', 'preview', 'status'])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.command == 'daemon':
        daemon()
    elif args.command == 'preview':
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
                sock.settimeout(2)
                sock.sendto(b'preview', str(RUNTIME / 'control.sock'))
            print('Animation requested (silent, automatically dismisses).')
        except OSError as error:
            raise SystemExit(f'{error}\nStart with: systemctl --user start computer-notification.service')
    else:
        try:
            print((RUNTIME / 'status.json').read_text())
        except FileNotFoundError:
            raise SystemExit('Not running')


if __name__ == '__main__':
    main()
