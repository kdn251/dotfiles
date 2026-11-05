#!/usr/bin/env python3
"""Keep the last rendered chat frame visible during a stream handoff."""
import ctypes,json,os,subprocess,sys,time
from pathlib import Path
ctypes.CDLL('libgtk4-layer-shell.so',mode=ctypes.RTLD_GLOBAL)
import gi
gi.require_version('Gtk','4.0');gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Gtk4LayerShell as Layer
from media_chat_fullscreen import read,ROOT

class Cover(Gtk.Application):
    def __init__(self,request):
        super().__init__(application_id='local.media.chat.cover',flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.request=request;self.started=time.monotonic();self.armed=False
        self.connect('activate',self.activate_cover)
    def activate_cover(self,_):
        r=self.request;m=r['monitor'];b=r['bounds']
        self.window=Gtk.ApplicationWindow(application=self)
        Layer.init_for_window(self.window);Layer.set_namespace(self.window,'media-chat-cover')
        Layer.set_layer(self.window,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(self.window,-1)
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.NONE)
        for monitor in Gdk.Display.get_default().get_monitors():
            if monitor.get_connector()==m['name']:Layer.set_monitor(self.window,monitor);break
        Layer.set_anchor(self.window,Layer.Edge.TOP,True);Layer.set_anchor(self.window,Layer.Edge.RIGHT,True)
        self.window.set_default_size(*b['size'])
        picture=Gtk.Picture.new_for_filename(r['image']);picture.set_content_fit(Gtk.ContentFit.FILL)
        self.window.set_child(picture)
        self.window.connect('map',lambda *_:GLib.timeout_add(40,self.ready))
        self.window.present();GLib.timeout_add(50,self.check)
    def ready(self):
        Path(self.request['ready']).touch();return False
    def check(self):
        r=self.request
        try:
            if Path('/tmp/twitch-session.id').read_text().strip()!=r['session']:self.quit();return False
            if time.monotonic()-self.started>60:self.quit();return False
            clients=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))
            monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
            m=next((m for m in monitors if m['id']==r['monitor']['id']),{})
            visible=m.get('activeWorkspace',{}).get('id')==r['workspace']
            self.window.set_visible(visible)
            state=read()
            if state and state.get('transition',{}).get('session')==r['session']:self.armed=True
            if not self.armed:return True
            if not any(c.get('class')=='mpv' and c.get('fullscreen') for c in clients):
                self.quit();return False
            if state and not state.get('transition'):
                player=next((c for c in clients if c.get('pid')==state['player']['pid']),None)
                chat=next((c for c in clients if c.get('address')==state['chat']['address']),None)
                if player and not player.get('fullscreen'):self.quit();return False
                if chat and m.get('specialWorkspace',{}).get('name')=='special:chatterino_chat':
                    loaded=chat.get('class')=='com.chatterino.chatterino' or (ROOT/f"media-chat-ready-{chat['pid']}").exists()
                    if loaded:self.quit();return False
            elif not state and time.monotonic()-self.started>2:
                self.quit();return False
        except (OSError,ValueError,subprocess.SubprocessError):pass
        return True

if __name__=='__main__':
    path=Path(sys.argv[1]);request=json.loads(path.read_text())
    try:Cover(request).run([sys.argv[0]])
    finally:
        for name in (request['image'],request['ready'],str(path)):Path(name).unlink(missing_ok=True)
