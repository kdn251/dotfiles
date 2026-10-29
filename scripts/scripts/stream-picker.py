#!/usr/bin/env python3
"""Stream menu with a live, platform-colored prompt; stdout is the selection."""
import ctypes
import os

# This small menu needs no Vulkan renderer startup; GL maps much faster.
os.environ.setdefault("GSK_RENDERER", "gl")
import sys
from pathlib import Path
import stream_menu_metadata

# Load before GTK/Wayland so layer-shell can intercept surface creation.
ctypes.CDLL('libgtk4-layer-shell.so', mode=ctypes.RTLD_GLOBAL)
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, Gio, Gtk, Gtk4LayerShell as Layer, Pango, GLib, Gsk, Graphene

PLATFORMS = {
    't': ('Twitch', '\ue900', '#9146ff'),
    'r': ('Rumble', '\ue902', '#85c742'),
    'y': ('YouTube', '\ue901', '#ff0033'),
    'k': ('Kick', '\ue903', '#53fc18'),
}


def platform(text):
    return text[0].lower() if len(text) >= 2 and text[1] == '/' and text[0].lower() in 'ryk' else 't'


def matches(query, label):
    # Keep subsequence matching for fast keyboard searches.
    letters = iter(label.casefold())
    return all(any(candidate == char for candidate in letters) for char in query.casefold())


def parse_menu(data):
    items = []
    seen = set()
    for line in data.splitlines():
        value, _, metadata = line.partition('\0')
        label, sep, identity = value.partition('\t')
        if not sep:
            continue
        icon = metadata.removeprefix('icon\x1f') if metadata.startswith('icon\x1f') else ''
        service = next((key for key, (name, _, _) in PLATFORMS.items()
                        if identity.endswith(f'({name})')), 't')
        key = (service, identity.split()[0].casefold())
        if key in seen:
            continue
        seen.add(key)
        items.append((label, identity, icon, service))
    return items


class RoundedAvatar(Gtk.Image):
    def do_snapshot(self, snapshot):
        bounds = Graphene.Rect().init(0, 0, self.get_width(), self.get_height())
        clip = Gsk.RoundedRect()
        clip.init_from_rect(bounds, 6)
        snapshot.push_rounded_clip(clip)
        Gtk.Image.do_snapshot(self, snapshot)
        snapshot.pop()


class Picker(Gtk.Application):
    def __init__(self, items, resident=False):
        super().__init__(application_id='local.stream.picker', flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.resident = resident
        self.reply = None
        self.prefetch_timer = None
        self.marquee_timer = None
        self.marquee_row = None
        self.metadata = stream_menu_metadata.load()
        self.items = items
        self.connect('activate', self.activate_picker)

    def activate_picker(self, _app):
        self.window = Gtk.ApplicationWindow(application=self, title='Streams')
        Layer.init_for_window(self.window)
        Layer.set_namespace(self.window, 'stream-picker')
        Layer.set_layer(self.window, Layer.Layer.OVERLAY)
        Layer.set_keyboard_mode(self.window, Layer.KeyboardMode.EXCLUSIVE)
        self.window.set_default_size(650, -1)
        css = Gtk.CssProvider()
        css.load_from_data(b'''
          window { background: transparent; }
          .picker { background: rgba(46,52,64,0.949019608); color: #eceff4;
                    border: 2px solid #88c0d0; border-radius: 15px; padding: 12px 18px;
                    font-family: "JetBrains Mono"; font-size: 14pt; }
          entry { background: transparent; color: #eceff4; border: none;
                  box-shadow: none; outline: none; padding: 0; min-height: 36px; }
          entry:focus-within { outline: none; box-shadow: none; }
          .picker list { background: transparent; color: #eceff4; }
          .picker row { background: transparent; color: #eceff4;
                        padding: 7px 8px; border-radius: 8px; min-height: 40px;
                        font-family: sans-serif; font-size: 12pt; }
          .picker row label { color: #eceff4; }
          .picker row:selected { background: #3b4252; color: #88c0d0; }
          .picker row:selected label { color: #eceff4; }
          .picker row .stream-name { font-weight: 700; }
          .picker row .stream-category { color: #88c0d0; font-size: 10pt; }
          .picker row .stream-title { color: #b5bdcc; font-size: 10.5pt; }
          .picker row .stream-viewers { color: #88c0d0; font-size: 11pt; font-weight: 700;
              background: transparent; padding: 0; }
          .picker row:selected { background: #3b4252; }
        ''')
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.add_css_class('picker')
        header = Gtk.Box(spacing=12)
        self.logo = Gtk.Label()
        self.logo.set_size_request(28, -1)
        header.append(self.logo)
        self.entry = Gtk.Entry(hexpand=True)
        self.entry.connect('changed', self.changed)
        self.entry.connect('activate', self.accept)
        header.append(self.entry)
        box.append(header)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True)
        self.list.connect('row-activated', self.row_activated)
        self.list.connect('row-selected', self.prefetch_selected)
        scroll = Gtk.ScrolledWindow()
        self.scroll = scroll
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.EXTERNAL)
        scroll.set_min_content_height(324)
        scroll.set_max_content_height(324)
        scroll.set_kinetic_scrolling(False)
        wheel = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        wheel.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        wheel.connect("scroll", self.scroll_rows)
        scroll.add_controller(wheel)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.list)
        box.append(scroll)
        self.window.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.window.add_controller(keys)
        self.changed(self.entry)
        if self.resident:
            self.hold()
            self.window.connect('close-request', self.close_request)
            start_server(self)
        else:
            self.anchor_search()
            self.window.present()
            self.entry.grab_focus()

    def anchor_search(self):
        # Center the initial full menu once, then keep its top edge fixed while
        # filtering changes the height. Horizontal centering stays automatic.
        display = Gdk.Display.get_default()
        monitors = display.get_monitors()
        monitor = Layer.get_monitor(self.window)
        try:
            import json
            import subprocess
            current = json.loads(subprocess.check_output(['hyprctl', 'monitors', '-j'], timeout=1))
            connector = next(item['name'] for item in current if item.get('focused'))
            monitor = next(monitors.get_item(i) for i in range(monitors.get_n_items())
                           if monitors.get_item(i).get_connector() == connector)
        except (OSError, ValueError, StopIteration, subprocess.SubprocessError):
            pass
        if monitor is None and monitors.get_n_items():
            monitor = monitors.get_item(0)
        if monitor is not None:
            Layer.set_monitor(self.window, monitor)
            height = self.window.get_child().measure(Gtk.Orientation.VERTICAL, 650)[1]
            Layer.set_anchor(self.window, Layer.Edge.TOP, True)
            Layer.set_margin(self.window, Layer.Edge.TOP,
                             max(12, (monitor.get_geometry().height - height) // 2))

    def close_request(self, *_):
        self.finish('')
        return True

    def show_request(self, data, reply):
        if self.reply is not None:
            reply('')
            self.window.present()
            return False
        self.reply = reply
        self.items = parse_menu(data)
        self.metadata = stream_menu_metadata.load()
        self.entry.set_text('')
        self.changed(self.entry)
        self.scroll.get_vadjustment().set_value(0)
        self.anchor_search()
        self.window.present()
        self.entry.grab_focus()
        self.warm_top_streams()
        return False

    def changed(self, entry):
        text = entry.get_text()
        service = platform(text)
        name, glyph, color = PLATFORMS[service]
        self.logo.set_markup(f'<span font_family="Stream Launcher Icons" size="18000" foreground="{color}">{glyph}</span>')
        self.logo.set_tooltip_text(name)
        query = text[2:].lstrip('@') if service != 't' else text
        while child := self.list.get_first_child():
            self.list.remove(child)
        results = []
        for item in self.items:
            label, identity, icon, item_service = item
            if service != 't' and item_service != service:
                continue
            info = stream_menu_metadata.details(label, identity, item_service, self.metadata)
            name, category, stream_title, viewers = info
            rank = stream_menu_metadata.search_rank(query, name, category, stream_title)
            if rank is not None:
                results.append((rank, item, info))
        # Stable sorting preserves favorites/order for ties and an empty search.
        for _, (label, identity, icon, item_service), info in sorted(results, key=lambda result: result[0]):
            name, category, stream_title, viewers = info
            row = Gtk.ListBoxRow()
            row.result = label + '\t' + identity
            content = Gtk.Box(spacing=10)
            avatar = RoundedAvatar(file=icon) if icon and Path(icon).is_file() else RoundedAvatar(icon_name="video-display-symbolic")
            avatar.set_pixel_size(36)
            avatar.set_valign(Gtk.Align.CENTER)
            content.append(avatar)
            words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5, hexpand=True)
            top = Gtk.Box(spacing=10)
            title = Gtk.Label(label=name, xalign=0)
            title.set_markup(stream_menu_metadata.highlight(name, query, fuzzy=True))
            title.add_css_class('stream-name')
            top.append(title)
            game = Gtk.Label(label=category, xalign=0, hexpand=True)
            game.set_ellipsize(Pango.EllipsizeMode.END)
            game.set_markup(stream_menu_metadata.highlight(category, query))
            game.add_css_class('stream-category')
            top.append(game)
            count = Gtk.Label(label=viewers.replace(" watching", ""), xalign=1)
            count.set_tooltip_text(viewers)
            count.set_valign(Gtk.Align.CENTER)
            count.set_yalign(0.5)
            count.set_visible(bool(viewers))
            count.add_css_class('stream-viewers')
            top.append(count)
            words.append(top)
            subtitle = Gtk.Label(label=stream_title or 'Live now', xalign=0, hexpand=True)
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle.add_css_class('stream-title')
            subtitle.set_tooltip_text(stream_title or label)
            words.append(subtitle)
            row.subtitle = subtitle
            row.full_title = stream_title or 'Live now'
            row.query = query
            subtitle.set_markup(stream_menu_metadata.highlight(row.full_title, query))
            content.append(words)
            row.set_child(content)
            self.list.append(row)
        rows = []
        child = self.list.get_first_child()
        while child:
            rows.append(child)
            child = child.get_next_sibling()
        self.row_height = max((r.measure(Gtk.Orientation.VERTICAL, -1)[1] for r in rows), default=54)
        for r in rows:
            r.set_size_request(-1, self.row_height)
        height = self.row_height * min(6, max(1, len(rows)))
        self.scroll.set_min_content_height(0)
        self.scroll.set_max_content_height(height)
        self.scroll.set_min_content_height(height)
        self.list.select_row(self.list.get_row_at_index(0))

    def scroll_rows(self, _controller, _dx, dy):
        adjustment = self.scroll.get_vadjustment()
        height = getattr(self, 'row_height', 54)
        step = 1 if dy > 0 else -1 if dy < 0 else 0
        adjustment.set_value(round(adjustment.get_value() / height) * height + step * height)
        return True

    def warm_top_streams(self):
        import subprocess
        channels = [identity.split()[0] for _, identity, _, service in self.items if service == 't'][:2]
        for name in channels:
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('twitch-stream-url.py')),
                              name, '--prefetch'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)

    def prefetch_selected(self, _list, row):
        if self.marquee_timer:
            GLib.source_remove(self.marquee_timer)
            self.marquee_timer = None
        if self.marquee_row:
            self.marquee_row.subtitle.set_markup(stream_menu_metadata.highlight(self.marquee_row.full_title, self.marquee_row.query))
        self.marquee_row = row
        if row:
            ticks = [0]
            def scroll_title():
                if not self.window.get_visible():
                    self.marquee_timer = None
                    return False
                ticks[0] += 1
                layout = row.subtitle.create_pango_layout(row.full_title)
                if layout.get_pixel_size()[0] > row.subtitle.get_width() and ticks[0] > 8:
                    text = row.full_title + '     •     '
                    offset = (ticks[0] - 8) % len(text)
                    row.subtitle.set_markup(stream_menu_metadata.highlight(text, row.query, offset=offset))
                return True
            self.marquee_timer = GLib.timeout_add(100, scroll_title)
        if self.prefetch_timer:
            GLib.source_remove(self.prefetch_timer)
            self.prefetch_timer = None
        if row is None:
            return
        identity = row.result.split('\t', 1)[1]
        if identity.endswith(('(YouTube)', '(Rumble)', '(Kick)')):
            return
        name = identity.split()[0]
        def warm():
            import subprocess
            self.prefetch_timer = None
            subprocess.Popen([sys.executable, str(Path(__file__).with_name('twitch-stream-url.py')),
                              name, '--prefetch'], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return False
        self.prefetch_timer = GLib.timeout_add(150, warm)

    def finish(self, value):
        if self.resident:
            self.window.set_visible(False)
            reply, self.reply = self.reply, None
            if reply:
                reply(value)
        else:
            if value:
                print(value, flush=True)
            self.quit()

    def row_activated(self, _list, row):
        self.finish(row.result)

    def accept(self, _entry):
        row = self.list.get_selected_row()
        self.finish(row.result if row else self.entry.get_text())

    def key_pressed(self, _controller, key, _code, modifiers):
        if key == Gdk.KEY_Escape:
            self.finish('')
            return True
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and modifiers & Gdk.ModifierType.SHIFT_MASK:
            self.finish(self.entry.get_text())
            return True
        if key in (Gdk.KEY_Down, Gdk.KEY_Up, Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab):
            row = self.list.get_selected_row()
            index = row.get_index() if row else -1
            step = -1 if key in (Gdk.KEY_Up, Gdk.KEY_ISO_Left_Tab) else 1
            target = self.list.get_row_at_index(max(0, index + step))
            if target:
                self.list.select_row(target)
                # Keep typing in the search entry after keyboard navigation.
                adjustment = self.scroll.get_vadjustment()
                # get_height() excludes CSS padding; scrolling uses the full
                # row pitch, otherwise the next row is clipped by 14 pixels.
                top = target.get_index() * self.row_height
                bottom = top + self.row_height
                if top < adjustment.get_value():
                    adjustment.set_value(top)
                elif bottom > adjustment.get_value() + adjustment.get_page_size():
                    adjustment.set_value(bottom - adjustment.get_page_size())
            return True
        return False


def start_server(picker):
    import json
    import socket
    import threading
    path = Path(os.environ['XDG_RUNTIME_DIR'])/'stream-picker.sock'
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX)
    server.bind(str(path))
    path.chmod(0o600)
    server.listen(4)

    def handle(client):
        with client:
            try:
                client.settimeout(5)
                with client.makefile('r') as source:
                    data = json.loads(source.readline())
                    event = threading.Event()
                    answer = []
                    def reply(value):
                        answer.append(value)
                        event.set()
                    GLib.idle_add(picker.show_request, data, reply)
                    event.wait()
                    client.sendall((json.dumps(answer[0])+'\n').encode())
            except (OSError, ValueError):
                pass

    def serve():
        while True:
            client, _ = server.accept()
            threading.Thread(target=handle, args=(client,), daemon=True).start()
    threading.Thread(target=serve, daemon=True).start()


if __name__ == '__main__':
    resident = '--daemon' in sys.argv
    if resident:
        import fcntl
        lock = (Path(os.environ['XDG_RUNTIME_DIR'])/'stream-picker.lock').open('w')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0)
    picker = Picker([] if resident else parse_menu(sys.stdin.read()), resident)
    picker.run([])
