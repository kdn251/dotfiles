"""The shared live GTK loading indicator for stream panes and previews."""
from gi.repository import Gtk


def create_spinner():
    spinner = Gtk.Spinner()
    spinner.set_size_request(48, 48)
    spinner.set_halign(Gtk.Align.CENTER)
    spinner.set_valign(Gtk.Align.CENTER)
    spinner.set_no_show_all(True)
    return spinner
