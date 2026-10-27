#!/usr/bin/env python3
"""Stream menu with a live, platform-colored prompt; stdout is the selection."""
import ctypes
import sys
from pathlib import Path

# Load before GTK/Wayland so layer-shell can intercept surface creation.
ctypes.CDLL('libgtk4-layer-shell.so', mode=ctypes.RTLD_GLOBAL)
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('Gtk4LayerShell', '1.0')
from gi.repository import Gdk, Gio, Gtk, Gtk4LayerShell as Layer, Pango

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
    for line in data.splitlines():
        value, _, metadata = line.partition('\0')
        label, sep, identity = value.partition('\t')
        if not sep:
            continue
        icon = metadata.removeprefix('icon\x1f') if metadata.startswith('icon\x1f') else ''
        service = next((key for key, (name, _, _) in PLATFORMS.items()
                        if identity.endswith(f'({name})')), 't')
        items.append((label, identity, icon, service))
    return items


class Picker(Gtk.Application):
    def __init__(self, items):
        super().__init__(application_id='local.stream.picker', flags=Gio.ApplicationFlags.NON_UNIQUE)
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
                        padding: 3px 6px; border-radius: 0; min-height: 29px; }
          .picker row label { color: #eceff4; }
          .picker row:selected { background: #3b4252; color: #88c0d0; }
          .picker row:selected label { color: #88c0d0; }
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
        scroll = Gtk.ScrolledWindow()
        self.scroll = scroll
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_min_content_height(350)
        scroll.set_max_content_height(350)
        scroll.set_propagate_natural_height(True)
        scroll.set_child(self.list)
        box.append(scroll)
        self.window.set_child(box)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed', self.key_pressed)
        self.window.add_controller(keys)
        self.changed(self.entry)
        self.window.present()
        self.entry.grab_focus()

    def changed(self, entry):
        text = entry.get_text()
        service = platform(text)
        name, glyph, color = PLATFORMS[service]
        self.logo.set_markup(f'<span font_family="Stream Launcher Icons" size="18000" foreground="{color}">{glyph}</span>')
        self.logo.set_tooltip_text(name)
        query = text[2:].lstrip('@') if service != 't' else text
        while child := self.list.get_first_child():
            self.list.remove(child)
        for label, identity, icon, item_service in self.items:
            if service != 't' and item_service != service:
                continue
            if not matches(query, label):
                continue
            row = Gtk.ListBoxRow()
            row.result = label + '\t' + identity
            content = Gtk.Box(spacing=10)
            avatar = Gtk.Image.new_from_file(icon) if icon and Path(icon).is_file() else Gtk.Image.new_from_icon_name('video-display-symbolic')
            avatar.set_pixel_size(28)
            content.append(avatar)
            title = Gtk.Label(label=label, xalign=0, hexpand=True)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            content.append(title)
            row.set_child(content)
            self.list.append(row)
        self.list.select_row(self.list.get_row_at_index(0))

    def finish(self, value):
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
            self.quit()
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
                top = target.get_allocation().y
                bottom = top + target.get_height()
                if top < adjustment.get_value():
                    adjustment.set_value(top)
                elif bottom > adjustment.get_value() + adjustment.get_page_size():
                    adjustment.set_value(bottom - adjustment.get_page_size())
            return True
        return False


if __name__ == '__main__':
    picker = Picker(parse_menu(sys.stdin.read()))
    picker.run([])
