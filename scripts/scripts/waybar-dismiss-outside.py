#!/usr/bin/env python3
"""Dismiss Waybar popups on a non-consuming Hyprland mouse binding."""
import json
import os
from pathlib import Path
import subprocess

RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))


def hypr(command):
    return json.loads(subprocess.check_output(
        ["hyprctl", "-j", command], text=True, timeout=2))


def contains(point, x, y, width, height):
    return x <= point["x"] < x + width and y <= point["y"] < y + height


def notification_hit(point, layer):
    # swaync's layer spans the screen height; only its scroll pane accepts
    # input. AT-SPI supplies the actual popup height in window coordinates.
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi
    Atspi.set_timeout(500, 500)
    desktop = Atspi.get_desktop(0)
    for i in range(desktop.get_child_count()):
        app = desktop.get_child_at_index(i)
        if app.get_name() != "swaync":
            continue
        for j in range(app.get_child_count()):
            frame = app.get_child_at_index(j)
            if not frame.get_state_set().contains(Atspi.StateType.SHOWING):
                continue
            for k in range(frame.get_child_count()):
                child = frame.get_child_at_index(k)
                if child.get_role() != Atspi.Role.SCROLL_PANE:
                    continue
                rect = child.get_component_iface().get_extents(Atspi.CoordType.WINDOW)
                if contains(point, layer["x"] + rect.x, layer["y"] + rect.y,
                            rect.width, rect.height):
                    return True
    return False


def main():
    point = hypr("cursorpos")
    layers = [layer for monitor in hypr("layers").values()
              for level in monitor["levels"].values() for layer in level]
    # Let module clicks perform their existing toggle/switch behavior.
    if any(layer["namespace"] == "waybar" and
           contains(point, layer["x"], layer["y"], layer["w"], layer["h"])
           for layer in layers):
        return

    panels = list(RUNTIME.glob("waybar-panel-*.notification"))
    if panels:
        inside = False
        for layer in layers:
            if layer["namespace"] == "swaync-notification-window":
                try:
                    inside |= notification_hit(point, layer)
                except Exception:
                    # Preserve button clicks if accessibility is unavailable.
                    inside |= contains(point, layer["x"], layer["y"], layer["w"], layer["h"])
        if not inside:
            for panel in panels:
                try:
                    notification_id = int(panel.read_text().strip())
                except (OSError, ValueError):
                    continue
                subprocess.run(["gdbus", "call", "--session", "--dest",
                                "org.freedesktop.Notifications", "--object-path",
                                "/org/freedesktop/Notifications", "--method",
                                "org.freedesktop.Notifications.CloseNotification",
                                str(notification_id)], stdout=subprocess.DEVNULL, timeout=2)

    for window in hypr("clients"):
        cls = window["class"]
        if cls not in {"calendar-float", "proton.vpn.app.gtk", "protonvpn-app"}:
            continue
        if window["workspace"]["name"].startswith("special:") or not window["mapped"]:
            continue
        if contains(point, *window["at"], *window["size"]):
            continue
        if cls == "calendar-float":
            subprocess.run(["hyprctl", "dispatch", "closewindow",
                            "address:" + window["address"]], stdout=subprocess.DEVNULL, timeout=2)
        else:
            subprocess.run([str(Path.home() / "scripts/protonvpn-waybar.sh"),
                            "hide-if-visible"], stdout=subprocess.DEVNULL, timeout=3)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
