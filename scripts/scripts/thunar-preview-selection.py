#!/usr/bin/env python3
"""Select previewed files via accessibility without activating the file manager."""
import json
import os
import sys
from pathlib import Path

import gi
gi.require_version('Atspi', '2.0')
from gi.repository import Atspi


def walk(node, path=()):
    yield node, path
    # File cells can be numerous; callers only need the view itself.
    if node.get_role_name() in ('tree table', 'table', 'layered pane'):
        return
    for i in range(node.get_child_count()):
        yield from walk(node.get_child_at_index(i), path + (i,))


def names(node):
    yield node.get_name()
    for child in node:
        yield from names(child)


def matching_child(view, filename):
    for i, child in enumerate(view):
        if filename in names(child):
            return i, child
    return None


def app():
    return next(a for a in Atspi.get_desktop(0) if a.get_name() == 'thunar')


def directory_matches(frame, directory):
    for node, _ in walk(frame):
        if node.get_role_name() == 'text' and 'Text' in node.get_interfaces():
            if Atspi.Text.get_text(node, 0, -1).rstrip('/') == directory.rstrip('/'):
                return True
    return False


def bind(filename):
    directory = str(Path(filename).parent)
    application = app()
    for frame_index, frame in enumerate(application):
        if not directory_matches(frame, directory):
            continue
        for view, path in walk(frame):
            if view.get_role_name() not in ('tree table', 'table', 'layered pane') or 'Selection' not in view.get_interfaces():
                continue
            match = matching_child(view, Path(filename).name)
            if match:
                return json.dumps({'pid': application.get_process_id(),
                                   'path': [frame_index, *path], 'directory': directory})
    raise RuntimeError('Could not locate the selected file in Thunar')


def select(binding, filename):
    target = json.loads(binding)
    if str(Path(filename).parent) != target['directory']:
        return
    node = app()
    if node.get_process_id() != target['pid']:
        return
    for depth, index in enumerate(target['path']):
        node = node.get_child_at_index(index)
        if depth == 0 and not directory_matches(node, target['directory']):
            return
    match = matching_child(node, Path(filename).name)
    if match is None:
        return
    index, cell = match
    Atspi.Selection.clear_selection(node)
    if 'Table' in node.get_interfaces():
        row = Atspi.Table.get_row_at_index(node, index)
        success = Atspi.Table.add_row_selection(node, row)
    else:
        success = Atspi.Selection.select_child(node, index)
    if not success:
        raise RuntimeError('Thunar refused selection')
    # Scroll the new selection into view without taking focus away from mpv.
    try:
        Atspi.Component.scroll_to(cell, Atspi.ScrollType.ANYWHERE)
    except gi.repository.GLib.Error:
        pass


if __name__ == '__main__':
    try:
        if sys.argv[1] == '--bind':
            print(bind(os.path.abspath(sys.argv[2])))
        else:
            select(sys.argv[2], os.path.abspath(sys.argv[3]))
    except (RuntimeError, StopIteration, gi.repository.GLib.Error) as exc:
        print(f'Preview selection: {exc}', file=sys.stderr)
        sys.exit(1)
