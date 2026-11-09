#!/usr/bin/env python3
"""Display the multi-view GTK spinner over a loading picker preview."""
import json
import os
import sys
import time
import threading
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell as Layer
from mpv_clip import Player
from stream_loading_spinner import create_spinner

pid, endpoint, bounds, monitor = int(sys.argv[1]), sys.argv[2], json.loads(sys.argv[3]), json.loads(sys.argv[4])
window = Gtk.Window()
Layer.init_for_window(window)
Layer.set_namespace(window, 'stream-preview-loading')
Layer.set_layer(window, Layer.Layer.OVERLAY)
Layer.set_keyboard_mode(window, Layer.KeyboardMode.NONE)
Layer.set_exclusive_zone(window, -1)
display = Gdk.Display.get_default()
for i in range(display.get_n_monitors()):
    target = display.get_monitor(i)
    if target.get_geometry().x == monitor['x'] and target.get_geometry().y == monitor['y']:
        Layer.set_monitor(window, target)
        break
for edge in (Layer.Edge.LEFT, Layer.Edge.TOP):
    Layer.set_anchor(window, edge, True)
x, y, width, height = bounds
Layer.set_margin(window, Layer.Edge.LEFT, x-monitor['x'])
Layer.set_margin(window, Layer.Edge.TOP, y-monitor['y'])
window.set_size_request(width, height)
window.get_style_context().add_class('pane')
css = Gtk.CssProvider()
css.load_from_data(b'window { background-color: black; } .pane spinner { color: white; }')
Gtk.StyleContext.add_provider_for_screen(window.get_screen(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
spinner = create_spinner()
window.add(spinner)
spinner.start()
spinner.show()
# Never intercept clicks intended for the preview or focus the menu.
window.connect('realize', lambda w: w.get_window().set_pass_through(True))


def watch():
    deadline = time.monotonic()+75
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
            player = Player(endpoint, pid)
            try:
                done = player.get('user-data/preview-ready') or player.get('user-data/preview-load-error')
            finally:
                player.close()
            if done:
                break
        except (OSError, ValueError):
            break
        time.sleep(.04)
    GLib.idle_add(Gtk.main_quit)

window.show()
threading.Thread(target=watch, daemon=True).start()
Gtk.main()
