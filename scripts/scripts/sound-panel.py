#!/usr/bin/env python3
"""Compact Waybar sound popup with a live output-volume slider."""
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import signal
import subprocess
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
from gi.repository import Gtk, Gdk, GLib, GtkLayerShell


def pactl(*args):
    return subprocess.check_output(['pactl',*args],text=True,timeout=3).strip()


def snapshot():
    name=pactl('get-default-sink')
    sinks=json.loads(pactl('-f','json','list','sinks'))
    sink=next(s for s in sinks if s['name']==name)
    volume=round(max(v['value'] for v in sink['volume'].values())/65536*100)
    return sinks,name,volume,sink['mute'],pactl('get-source-mute','@DEFAULT_SOURCE@').endswith('yes')


class Panel(Gtk.Window):
    def __init__(self):
        super().__init__(title='Sound')
        self.pool=ThreadPoolExecutor(max_workers=1)
        self.refreshing=False;self.updating=False;self.dragging=False;self.pending=0
        self.set_default_size(340,-1);self.set_resizable(False)
        GtkLayerShell.init_for_window(self)
        GtkLayerShell.set_namespace(self,'waybar-sound-panel')
        GtkLayerShell.set_layer(self,GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_keyboard_mode(self,GtkLayerShell.KeyboardMode.ON_DEMAND)
        for edge in (GtkLayerShell.Edge.TOP,GtkLayerShell.Edge.RIGHT):GtkLayerShell.set_anchor(self,edge,True)
        GtkLayerShell.set_margin(self,GtkLayerShell.Edge.TOP,6)
        GtkLayerShell.set_margin(self,GtkLayerShell.Edge.RIGHT,9)
        try:
            monitors=json.loads(subprocess.check_output(['hyprctl','-j','monitors'],text=True,timeout=2))
            focused=next(m for m in monitors if m.get('focused'))
            monitor=Gdk.Display.get_default().get_monitor_at_point(focused['x']+1,focused['y']+1)
            GtkLayerShell.set_monitor(self,monitor)
        except (OSError,ValueError,StopIteration):pass
        css=Gtk.CssProvider();css.load_from_data(b'''
        * { font-family: monospace; font-size: 10pt; letter-spacing: 0; }
        window { background: rgba(48,61,72,0.98); color: #e6edf2; border: 1px solid #819fa8; border-radius: 5px; }
        label { color: #e6edf2; }
        .heading { font-weight: bold; color: #ffffff; }
        .percentage { color: #b5c5ce; }
        button, combobox button { min-height: 22px; min-width: 0; padding: 4px 8px; background: #344550; color: #e6edf2; border: none; border-radius: 4px; box-shadow: none; text-shadow: none; }
        button:hover { background: #425967; }
        button label { font-family: sans-serif; font-size: 10pt; }
        button.close { min-width: 20px; min-height: 20px; padding: 0; border-radius: 12px; background: #4e6572; }
        button.close:hover { background: #617e8a; }
        button.close label { font-size: 12pt; }
        scale { min-height: 16px; padding: 5px 0; }
        scale trough { min-height: 4px; border: none; background: #1e2932; border-radius: 3px; }
        scale highlight { background: #8bd5ca; border: none; border-radius: 3px; }
        scale slider { background: #e6edf2; min-width: 12px; min-height: 12px; border: none; box-shadow: none; border-radius: 6px; margin: -4px; }
        combobox arrow { min-width: 12px; min-height: 12px; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);box.set_border_width(10);self.add(box)
        heading=Gtk.Box(spacing=8);box.pack_start(heading,False,False,0)
        title=Gtk.Label(label='Sound');title.get_style_context().add_class('heading');title.set_xalign(0);heading.pack_start(title,True,True,0)
        self.percent=Gtk.Label(label='—');self.percent.get_style_context().add_class('percentage');heading.pack_start(self.percent,False,False,0)
        close=Gtk.Button(label='×');close.get_style_context().add_class('close');close.connect('clicked',lambda _:self.close());heading.pack_start(close,False,False,0)
        self.slider=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1);self.slider.set_draw_value(False)
        self.slider.connect('value-changed',self.changed)
        self.slider.connect('button-press-event',lambda *_:self.drag(True))
        self.slider.connect('button-release-event',lambda *_:self.drag(False))
        box.pack_start(self.slider,False,False,0)
        self.outputs=Gtk.ComboBoxText();self.outputs.connect('changed',self.output_changed);box.pack_start(self.outputs,False,False,0)
        self.output_names=[]
        buttons=Gtk.Box(spacing=8);box.pack_start(buttons,False,False,0)
        self.mute=Gtk.Button(label='Mute output');self.mic=Gtk.Button(label='Mute microphone')
        self.mute.connect('clicked',lambda _:self.action(lambda:pactl('set-sink-mute','@DEFAULT_SINK@','toggle')))
        self.mic.connect('clicked',lambda _:self.action(lambda:pactl('set-source-mute','@DEFAULT_SOURCE@','toggle')))
        for button in (self.mute,self.mic):buttons.pack_start(button,True,True,0)
        settings=Gtk.Button(label='Volume Control…');settings.set_tooltip_text('Adjust volumes for individual applications');settings.connect('clicked',self.settings);box.pack_start(settings,False,False,0)
        self.connect('key-press-event',lambda _,e:self.close() if e.keyval==Gdk.KEY_Escape else False)
        self.connect('destroy',lambda *_:Gtk.main_quit())
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,lambda:self.close())
        self.refresh();GLib.timeout_add(800,self.refresh)
        self.show_all()

    def drag(self,value):
        self.dragging=value
        return False

    def action(self,fn):
        def work():
            try:fn()
            except (OSError,subprocess.SubprocessError):pass
            GLib.idle_add(lambda:(self.refresh(),False)[1])
        self.pool.submit(work)

    def changed(self,slider):
        if self.updating:return
        value=round(slider.get_value());self.percent.set_text(f'{value}%')
        if not self.pending:self.pending=GLib.timeout_add(50,self.apply_volume)

    def apply_volume(self):
        self.pending=0;value=round(self.slider.get_value())
        self.action(lambda:pactl('set-sink-volume','@DEFAULT_SINK@',f'{value}%'))
        return False

    def output_changed(self,combo):
        if self.updating or not combo.get_active_id():return
        name=combo.get_active_id()
        def switch():
            pactl('set-default-sink',name)
            for stream in json.loads(pactl('-f','json','list','sink-inputs')):
                pactl('move-sink-input',str(stream['index']),name)
        self.action(switch)

    def refresh(self):
        if self.refreshing:return True
        self.refreshing=True
        def work():
            try:data=snapshot()
            except (OSError,ValueError,StopIteration,subprocess.SubprocessError):data=None
            GLib.idle_add(self.update,data)
        self.pool.submit(work)
        return True

    def update(self,data):
        self.refreshing=False
        if data is None:return False
        sinks,name,volume,muted,mic_muted=data;self.updating=True
        if not self.dragging and not self.pending:
            self.slider.set_value(min(100,volume));self.percent.set_text(f'{volume}%'+(' · muted' if muted else ''))
        names=[(s['name'],s['description']) for s in sinks]
        if names!=self.output_names:
            self.outputs.remove_all()
            for ident,label in names:self.outputs.append(ident,label[:30])
            self.output_names=names
        self.outputs.set_active_id(name)
        self.mute.set_label('Unmute output' if muted else 'Mute output')
        self.mic.set_label('Unmute microphone' if mic_muted else 'Mute microphone')
        self.updating=False
        return False

    def settings(self,_):
        subprocess.Popen(['pavucontrol','--tab=1'],start_new_session=True,close_fds=True)
        self.close()


if __name__=='__main__':
    panel=Panel();Gtk.main()
    panel.pool.shutdown(wait=False,cancel_futures=True)
    pidfile=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'waybar-panel-sound.pid'
    try:
        if pidfile.read_text().strip()==str(os.getpid()):pidfile.unlink()
    except OSError:pass
