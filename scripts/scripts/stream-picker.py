#!/usr/bin/env python3
"""Stream menu with a live, platform-colored prompt; stdout is the selection."""
import ctypes
import os

# This small menu needs no Vulkan renderer startup; GL maps much faster.
os.environ.setdefault("GSK_RENDERER", "gl")
import sys
from pathlib import Path
import stream_menu_metadata
from stream_preview import Preview
import stream_saved

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
        self.preview_timer = None
        self.preview = None
        self.preview_result = None
        self.marquee_timer = None
        self.marquee_row = None
        self.metadata = stream_menu_metadata.load()
        self.items = items
        self.connect('activate', self.activate_picker)
        GLib.timeout_add(100, self.check_preview)
        GLib.timeout_add_seconds(1, self.refresh_uptimes)

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
          .preview-hint { font-size: 10pt; color: #b5bdcc; }
          .picker list { background: transparent; color: #eceff4; }
          .picker row { background: transparent; color: #eceff4;
                        padding: 7px 8px; border-radius: 8px; min-height: 40px;
                        font-family: sans-serif; font-size: 12pt; }
          .picker row label { color: #eceff4; }
          .picker row:selected { background: #3b4252; color: #88c0d0; }
          .picker row:selected label { color: #eceff4; }
          .picker row .stream-name { font-weight: 700; }
          .picker row .stream-category { color: #88c0d0; font-size: 10pt; }
          .picker row .stream-uptime { color: #88c0d0; font-size: 11pt; padding: 0; }
          .picker row .stream-title { color: #b5bdcc; font-size: 10.5pt; }
          .picker row .stream-viewers { color: #ff8280; font-size: 11pt; font-weight: 700;
              background: transparent; padding: 0; }
          .picker row:selected .stream-viewers { color: #ff8280; }
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
        self.preview_hint = Gtk.Label(label='', xalign=0)
        self.preview_hint.set_visible(False)
        self.preview_hint.add_css_class('preview-hint')
        self.preview_hint.set_ellipsize(Pango.EllipsizeMode.END)
        self.preview_hint.set_max_width_chars(65)
        box.append(self.preview_hint)
        self.window.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.window.add_controller(keys)
        import subprocess
        subprocess.run(['hyprctl','keyword','windowrule','float on, no_initial_focus on, opaque on, opacity 1.0 override 1.0 override, size 480 270, match:class ^(stream-preview)$'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
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
            geometry = monitor.get_geometry()
            self.preview_monitor = (geometry.x, geometry.y, geometry.width, geometry.height)
            Layer.set_anchor(self.window, Layer.Edge.LEFT, False)
            Layer.set_anchor(self.window, Layer.Edge.RIGHT, False)
            Layer.set_margin(self.window, Layer.Edge.LEFT, 0)
            height = self.window.get_child().measure(Gtk.Orientation.VERTICAL, 650)[1]
            top = max(12, (geometry.height-height)//2)
            self.preview_bounds = (geometry.x+(geometry.width-480)//2,
                geometry.y+top+height+14, 480, 270)
            Layer.set_anchor(self.window, Layer.Edge.TOP, True)
            Layer.set_margin(self.window, Layer.Edge.TOP, top)

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
            hover = Gtk.EventControllerMotion()
            hover.connect('enter', lambda _controller, _x, _y, current=row: self.list.select_row(current))
            row.add_controller(hover)
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
            count = Gtk.Label(label=viewers, xalign=1)
            count.set_tooltip_text(viewers.removeprefix("􀀁 ") + " viewers")
            count.set_valign(Gtk.Align.END)
            count.set_yalign(1.0)
            count.set_visible(bool(viewers))
            count.add_css_class('stream-viewers')
            top.append(count)
            row.stream_data = self.metadata.get(item_service, {}).get(name.casefold(), {})
            row.uptime = Gtk.Label(label=stream_menu_metadata.uptime(row.stream_data), xalign=1)
            row.uptime.add_css_class('stream-uptime')
            row.uptime.set_valign(Gtk.Align.END)
            row.uptime.set_yalign(1.0)
            row.uptime.set_visible(bool(row.uptime.get_text()))
            top.append(row.uptime)
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

    def show_status(self, text):
        if getattr(self, 'status_timer', None):
            GLib.source_remove(self.status_timer)
        self.preview_hint.set_text(text)
        self.preview_hint.set_visible(True)
        def clear():
            self.preview_hint.set_visible(False)
            self.status_timer=None
            return False
        self.status_timer=GLib.timeout_add(3000,clear)

    def save_streamer(self, _button):
        try:
            name, added = stream_saved.save(self.entry.get_text())
            self.show_status(name + (' saved' if added else ' is already saved'))
            if added:
                import subprocess
                subprocess.Popen([str(Path.home()/'scripts/update-live-list.sh')],stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        except (OSError,ValueError) as error:
            self.show_status(str(error))

    def schedule_preview(self, row):
        if self.preview_timer:
            GLib.source_remove(self.preview_timer);self.preview_timer=None
        if self.preview:
            self.preview.stop();self.preview=None
        self.preview_result = row.result if row else None
        if row is None:return
        def start():
            self.preview_timer=None
            if not self.window.get_visible() or self.list.get_selected_row()!=row:return False
            identity=row.result.split('\t',1)[1]
            name=identity.split()[0]
            service=next((s for s in ('YouTube','Rumble','Kick') if identity.endswith('('+s+')')),'Twitch')
            channel=row.stream_data.get('channel') or stream_saved.BASES[service]+name
            bounds=self.preview_bounds
            try:
                import json,subprocess
                layers=json.loads(subprocess.check_output(['hyprctl','-j','layers'],timeout=1))
                panel=next(layer for monitor in layers.values() for level in monitor['levels'].values() for layer in level
                           if layer.get('namespace')=='stream-picker' and layer.get('pid')==os.getpid())
                mx,my,mw,mh=self.preview_monitor
                right=panel['x']+panel['w']+14
                space=mx+mw-right-12
                if space>=240:
                    width=min(480,space)
                    bounds=(right,panel['y'],width,round(width*9/16))
                else:
                    below=my+mh-(panel['y']+panel['h']+14)-12
                    above=panel['y']-my-26
                    height=min(270,max(60,max(below,above)))
                    width=min(480,round(height*16/9),mw-24)
                    height=round(width*9/16)
                    y=panel['y']+panel['h']+14 if below>=above else panel['y']-height-14
                    bounds=(mx+(mw-width)//2,y,width,height)
            except (OSError,ValueError,KeyError,StopIteration,subprocess.SubprocessError):pass
            self.preview=Preview(name,service,channel,bounds)
            self.preview.start()
            return False
        self.preview_timer=GLib.timeout_add(550,start)

    def check_preview(self):
        preview=self.preview
        if preview and self.window.get_visible():
            if preview.accepted.exists():
                self.finish(self.preview_result)
        return True

    def refresh_uptimes(self):
        if hasattr(self, 'list'):
            row = self.list.get_first_child()
            while row:
                if hasattr(row, 'uptime'):
                    text = stream_menu_metadata.uptime(row.stream_data)
                    row.uptime.set_text(text)
                    row.uptime.set_visible(bool(text))
                row = row.get_next_sibling()
        return True

    def scroll_rows(self, _controller, _dx, dy):
        adjustment = self.scroll.get_vadjustment()
        height = getattr(self, 'row_height', 54)
        step = 1 if dy > 0 else -1 if dy < 0 else 0
        adjustment.set_value(round(adjustment.get_value() / height) * height + step * height)
        row = self.list.get_selected_row()
        target = self.list.get_row_at_index(max(0, (row.get_index() if row else 0) + step))
        if target:self.list.select_row(target)
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
        self.schedule_preview(row)
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
        name = identity.split()[0]
        service = next((s for s in ('YouTube', 'Rumble', 'Kick') if identity.endswith('('+s+')')), 'Twitch')
        if service == 'Twitch':
            command = [sys.executable, str(Path(__file__).with_name('twitch-stream-url.py')), name, '--prefetch']
        else:
            channel = self.metadata.get(service[0].lower(), {}).get(name.casefold(), {}).get('channel')
            if not channel:
                return
            command = [sys.executable, str(Path(__file__).with_name('stream-playback-url.py')), service, channel, '--prefetch']
        def warm():
            import subprocess
            self.prefetch_timer = None
            if not self.window.get_visible(): return False
            subprocess.Popen(command, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            return False
        self.prefetch_timer = GLib.timeout_add(150, warm)

    def finish(self, value):
        if self.preview_timer:
            GLib.source_remove(self.preview_timer);self.preview_timer=None
        if self.preview:
            if not value or value != self.preview_result or not self.preview.handoff():
                self.preview.stop()
            self.preview=None
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
        if key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter) and modifiers & Gdk.ModifierType.CONTROL_MASK:
            self.save_streamer(None)
            return True
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
