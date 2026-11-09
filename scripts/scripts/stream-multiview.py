#!/usr/bin/env python3
"""An equal-cell layer above an existing fullscreen player; its first cell stays native."""
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import gi
gi.require_version('Gtk','3.0')
gi.require_version('GtkLayerShell','0.1')
from gi.repository import Gtk,Gdk,GLib,GtkLayerShell as Layer
import stream_menu_metadata as metadata
from stream_multiview import ROOT,send,channel,cells,neighbor,mpv_key
from stream_multiview_video import Video
from media_chat_fullscreen import ipc,socket_for
import media_chat_fullscreen as chat
from stream_preview import resolve as resolve_twitch

SCRIPTS=Path(__file__).resolve().parent


def clients():return json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))


def resolve(name,service,page):
    if service=='Twitch':return resolve_twitch(name,service,page)
    result=subprocess.run([sys.executable,str(SCRIPTS/'stream-playback-url.py'),service,page],
                          capture_output=True,text=True,check=True,timeout=60)
    data=json.loads(result.stdout)
    return dict(url=data.get('playback_url') or data['url'],
                page=data['url'] if service=='YouTube' else data.get('page_url',page),
                context=dict(data,name=name,service=service,channel=page,quality='best'))


class Theater:
    def __init__(self,pid,row):
        ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.pid=pid;self.closed=False;self.selected=0;self.entries=[];self.last_layout=None
        self.zoomed=False;self.suspended=False;self.blank=None
        self.drag_source=None;self.drag_audio=None;self.dragging=False
        self.metadata=metadata.load();self.metadata_updated=time.monotonic()
        player=next(c for c in clients() if c['pid']==pid and c.get('fullscreen'))
        self.player=player;self.state={'player':player,'socket':socket_for(player)}
        if self.get('user-data/multiview-bindings')!=3:
            ipc(self.state,'load-script',str(Path.home()/'.config/mpv/scripts/stream-multiview.lua'))
        self.original_layout=self.get('user-data/media-panel-layout') or {}
        self.original_volume=self.get('volume') or 100
        self.original_brightness=self.get('brightness') or 0
        self.original_keep_open=self.get('keep-open') or 'no'
        self.set('keep-open','yes')
        self.owner_masked=False
        self.original_align={axis:self.get('video-align-'+axis) or 0 for axis in ('x','y')}
        previous=chat.read()
        self.chat_open=bool(previous and previous.get('player',{}).get('pid')==pid)
        if self.chat_open:
            chat.restore(previous,clients(),hide=True,animate=False)
            chat.PREFERENCE.unlink(missing_ok=True)
        self.original=dict(name=self.get('user-data/stream-name'),service=self.get('user-data/stream-service'),
            title=self.get('force-media-title') or '',url=self.get('path'),page=self.get('user-data/stream-page') or '')
        self.entries=[dict(self.original,video=None,ready=True,slot=0)]
        self.window=Gtk.Window(title='Stream theater')
        self.window.connect('delete-event',lambda *_:(self.close_session(),True)[1])
        self.window.set_app_paintable(True)
        visual=self.window.get_screen().get_rgba_visual()
        if visual:self.window.set_visual(visual)
        Layer.init_for_window(self.window);Layer.set_namespace(self.window,'stream-multiview')
        Layer.set_layer(self.window,Layer.Layer.OVERLAY);Layer.set_exclusive_zone(self.window,-1)
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.ON_DEMAND)
        for edge in (Layer.Edge.LEFT,Layer.Edge.RIGHT,Layer.Edge.TOP,Layer.Edge.BOTTOM):Layer.set_anchor(self.window,edge,True)
        monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
        self.monitor=next(m for m in monitors if m['id']==player['monitor'])
        display=Gdk.Display.get_default()
        for i in range(display.get_n_monitors()):
            monitor=display.get_monitor(i)
            if monitor.get_model()==self.monitor.get('model') or monitor.get_geometry().x==self.monitor['x']:
                Layer.set_monitor(self.window,monitor);break
        css=Gtk.CssProvider();css.load_from_data(b'''
window { background-color: transparent; }
.pane spinner { color: white; }
.pane { border: none; padding: 0; margin: 0; }
.audio-indicator { background: rgba(20,20,24,.8); border-radius: 6px; padding: 4px 7px; color: white; font-size: 15px; }
''')
        Gtk.StyleContext.add_provider_for_screen(self.window.get_screen(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.grid=Gtk.Grid();self.grid.set_row_homogeneous(True);self.grid.set_column_homogeneous(True)
        self.window.add(self.grid);self.window.connect('key-press-event',self.key)
        self.endpoint=ROOT/f'{pid}.sock';self.endpoint.unlink(missing_ok=True)
        self.server=socket.socket(socket.AF_UNIX);self.server.bind(str(self.endpoint));self.server.listen(8)
        os.chmod(self.endpoint,0o600)
        threading.Thread(target=self.listen,daemon=True).start()
        self.set('user-data/stream-multiview',True)
        self.add(row)
        self.timer=GLib.timeout_add(80,self.tick)
        threading.Thread(target=self.observe_fullscreen,daemon=True).start()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self.finish)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGINT,self.finish)

    def get(self,key):
        try:return ipc(self.state,'get_property',key)
        except ValueError:return None
    def set(self,key,value):return ipc(self.state,'set_property',key,value)

    def observe_fullscreen(self):
        # Wake the layout immediately, instead of waiting for compositor polling.
        from mpv_clip import Player
        observer=None
        try:
            observer=Player(self.state['socket'],self.pid)
            observer.command('observe_property',909,'fullscreen')
            observer.command('observe_property',910,'eof-reached')
            observer.socket.settimeout(None)
            for line in observer.stream:
                if self.closed:break
                event=json.loads(line)
                if event.get('event')=='property-change' and event.get('name')=='eof-reached' and event.get('data') is True:
                    GLib.idle_add(self.stream_ended,self.entries[0],'eof')
                if event.get('event')=='end-file' and event.get('reason')=='eof':
                    GLib.idle_add(self.stream_ended,self.entries[0],'eof')
                if event.get('event')=='playback-restart':GLib.idle_add(self.native_ready)
                if event.get('event')=='shutdown':
                    GLib.idle_add(lambda:self.finish(restore=False));break
                if event.get('event')=='property-change' and event.get('name')=='fullscreen':
                    GLib.idle_add(lambda:(self.tick(),False)[1])
        except (OSError,ValueError):pass
        finally:
            if observer:observer.close()

    def listen(self):
        while not self.closed:
            try:
                connection,_=self.server.accept()
                with connection:
                    connection.settimeout(.5);data=b''
                    while b'\n' not in data and len(data)<16384:
                        chunk=connection.recv(4096)
                        if not chunk:break
                        data+=chunk
                    message=json.loads(data)
                GLib.idle_add(self.action,message)
            except (OSError,ValueError):
                if self.closed:return

    def action(self,message):
        action=message.get('action')
        if action=='add':self.add(message['row'])
        elif action=='replace':self.replace(message['row'])
        elif action=='move':self.move_focus(message['direction'])
        elif action=='close':self.close_selected()
        elif action=='quit':self.close_session()
        elif action=='exit':self.toggle_fullscreen()
        elif action=='key':self.player_key(message['key'])
        elif action=='zoom':self.player_key('ENTER')
        elif action=='grid':self.player_key('ESC')
        return False

    def pane_positions(self):
        places=cells(len(self.entries))
        return [places[e.get('slot',i)] for i,e in enumerate(self.entries)]

    def move_focus(self,direction):
        positions=self.pane_positions();x,y=positions[self.selected]
        dx,dy={'h':(-1,0),'l':(1,0),'k':(0,-1),'j':(0,1)}[direction]
        self.select(next((i for i,p in enumerate(positions) if p==(x+dx,y+dy)),self.selected))

    def drag_begin(self,entry,x,y):
        if self.zoomed or self.suspended or entry.get('card_hover'):return
        self.drag_source=entry;self.drag_origin=(int(x),int(y));self.drag_audio=self.entries[self.selected];self.dragging=False

    def drag_update(self,dx,dy):
        if self.drag_source and dx*dx+dy*dy>64:self.dragging=True

    def swap_panes(self,first,second):
        if first is second:return
        first['slot'],second['slot']=second.get('slot',self.entries.index(second)),first.get('slot',self.entries.index(first))
        self.arrange();self.last_layout=None;self.tick()

    def drag_end(self,entry,dx,dy):
        if self.drag_source is entry and self.dragging:
            origin=entry['widget'].translate_coordinates(self.grid,*self.drag_origin)
            if origin:
                px,py=origin[0]+dx,origin[1]+dy
                for other in self.entries:
                    widget=other['widget'];point=widget.translate_coordinates(self.grid,0,0)
                    if point and point[0]<=px<point[0]+widget.get_allocated_width() and point[1]<=py<point[1]+widget.get_allocated_height():
                        self.swap_panes(entry,other);break
            self.suppress_click_until=time.monotonic()+.2
            if self.drag_audio in self.entries:self.select(self.entries.index(self.drag_audio))
        self.drag_source=None;self.dragging=False

    def stream_ended(self,entry,reason):
        if self.closed or entry not in self.entries:return False
        if reason=='error' and not entry.get('ready'):
            self.failed(entry);return False
        if reason!='eof':return False
        if time.monotonic()<entry.get('switching_until',0):
            if not entry.get('end_check_pending'):
                entry['end_check_pending']=True
                def check():
                    entry['end_check_pending']=False
                    if self.closed or entry not in self.entries:return False
                    eof=(entry['video'].get('eof-reached')=='yes' or entry['video'].get('idle-active')=='yes') if entry.get('video') else (self.get('eof-reached') or self.get('idle-active'))
                    if eof:self.stream_ended(entry,'eof')
                    return False
                GLib.timeout_add(2100,check)
            return False
        if len(self.entries)==1:self.close_session()
        else:self.remove(self.entries.index(entry))
        return False

    def pane(self,entry):
        box=Gtk.EventBox();box.set_visible_window(bool(entry.get('video')));box.get_style_context().add_class('pane')
        if entry.get('video'):box.override_background_color(Gtk.StateFlags.NORMAL,Gdk.RGBA(0,0,0,1))
        box.set_above_child(True)
        box.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.POINTER_MOTION_MASK|Gdk.EventMask.LEAVE_NOTIFY_MASK)
        overlay=Gtk.Overlay();box.add(overlay)
        body=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);overlay.add(body)
        if entry.get('video'):body.pack_start(entry['video'],True,True,0)
        else:body.pack_start(Gtk.Box(),True,True,0)
        box.connect('button-press-event',lambda _,event:self.card_click(entry,event,'down'))
        box.connect('button-release-event',lambda _,event:self.card_click(entry,event,'up'))
        indicator=Gtk.Label(label='🔊');indicator.get_style_context().add_class('audio-indicator')
        indicator.set_halign(Gtk.Align.END);indicator.set_valign(Gtk.Align.START)
        indicator.set_margin_top(10);indicator.set_margin_end(10);indicator.set_no_show_all(True)
        overlay.add_overlay(indicator);overlay.set_overlay_pass_through(indicator,True)
        spinner=Gtk.Spinner();spinner.set_size_request(48,48)
        spinner.set_halign(Gtk.Align.CENTER);spinner.set_valign(Gtk.Align.CENTER);spinner.set_no_show_all(True)
        overlay.add_overlay(spinner);overlay.set_overlay_pass_through(spinner,True)
        entry.update(widget=box,indicator=indicator,spinner=spinner)
        self.update_loading(entry)
        box.connect('motion-notify-event',lambda _,event:self.hover_details(entry,event))
        box.connect('leave-notify-event',lambda *_:self.card_command(entry,'script-message','stream-card-hover','no'))
        box.connect('size-allocate',lambda *_:GLib.idle_add(self.reposition_overlay,entry))
        drag=Gtk.GestureDrag.new(box);drag.set_button(1);drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        drag.connect('drag-begin',lambda gesture,x,y:self.drag_begin(entry,x,y))
        drag.connect('drag-update',lambda gesture,x,y:self.drag_update(x,y))
        drag.connect('drag-end',lambda gesture,x,y:self.drag_end(entry,x,y))
        entry['drag']=drag
        box.show_all()
        # Realize the children normally, but never let parent show_all reveal
        # feeds that arrange() deliberately hid in windowed/expanded mode.
        box.set_no_show_all(True);box.hide()
        return box

    def update_loading(self,entry):
        spinner=entry.get('spinner')
        if spinner is None:return
        loading=not entry.get('ready') and not entry.get('failed')
        if loading:spinner.start();spinner.show()
        else:spinner.stop();spinner.hide()

    def native_ready(self):
        if self.closed:return False
        entry=self.entries[0]
        if entry.get('waiting_native_url') and self.get('path')==entry['waiting_native_url']:
            entry.pop('waiting_native_url',None);self.loaded(entry)
        return False

    def reposition_overlay(self,entry):
        if not self.closed and entry in self.entries:self.position_overlays(entry)
        return False

    def position_overlays(self,entry):
        widget=entry['widget'];w=widget.get_allocated_width();h=widget.get_allocated_height()
        video=entry.get('video')
        aspect=entry.get('aspect',16/9)
        if video:
            try:aspect=float(video.get('video-params/aspect') or aspect)
            except ValueError:pass
        elif not entry.get('aspect'):
            aspect=float(self.get('video-params/aspect') or aspect)
        entry['aspect']=aspect
        vw=min(w,h*aspect);vh=vw/aspect
        i=self.entries.index(entry);x,y=self.pane_positions()[i]
        single=self.zoomed or self.suspended
        if single:x=y=0
        vx=(w-vw)/2 if single else (w-vw if x==0 else 0)
        vy=(h-vh)/2 if single or len(self.entries)<3 else (h-vh if y==0 else 0)
        entry['video_rect']=(vx,vy,vw,vh)
        entry['indicator'].set_margin_top(max(0,round(vy+8)))
        entry['indicator'].set_margin_end(max(0,round(w-vx-vw+8)))
        # Native pane zero renders into the full MPV canvas; embedded panes
        # render into their own GLArea. Give the shared OSC the right viewport.
        if video:
            # Match ordinary MPV: the card sits at the pane's bottom,
            # not above its bottom letterbox area.
            viewport=(vx/max(1,w),0,vw/max(1,w),1)
        else:
            layout=self.get('user-data/media-panel-layout') or {}
            left=float(layout.get('left',0))
            columns=1 if single else 2;rows=2 if len(self.entries)>2 and not single else 1
            viewport=(left+(x+vx/max(1,w))*(1-left)/columns,y/rows,
                      vw/max(1,w)*(1-left)/columns,1/rows)
        card_scale=max(1,self.window.get_allocated_height()/max(1,h)) if video and not self.suspended else 1
        viewport=(*viewport,card_scale)
        if entry.get('card_viewport')!=viewport:
            entry['card_viewport']=viewport
            self.card_command(entry,'script-message','stream-card-viewport',*viewport)

    def card_command(self,entry,*args):
        if self.closed:return False
        try:
            if entry.get('video'):entry['video'].command(*args)
            else:ipc(self.state,*args)
        except (OSError,ValueError,RuntimeError):pass
        return False

    def update_card(self,entry):
        video=entry.get('video')
        if not video:return
        data=self.metadata.get(entry['service'][0].lower(),{}).get(entry['name'].casefold(),{})
        title=metadata.format_playback_title(entry['name'],data,data.get('title') or entry.get('title',''))
        properties={'user-data/stream-name':entry['name'],'user-data/stream-service':entry['service'],
                    'user-data/stream-page':entry.get('page',''),'user-data/stream-uptime':metadata.uptime(data),
                    'force-media-title':title}
        for key,value in properties.items():
            if entry.get('card_properties',{}).get(key)!=value:video.set(key,value)
        entry['card_properties']=properties

    def card_mouse(self,entry,event,mode=None):
        widget=entry['widget'];scale=widget.get_scale_factor()
        x,y=event.x,event.y
        if not entry.get('video'):
            left=float((self.get('user-data/media-panel-layout') or {}).get('left',0))
            total_width=self.window.get_allocated_width()/max(.01,1-left)
            col,row=self.pane_positions()[0]
            if self.zoomed or self.suspended:col=row=0
            x+=total_width*left+col*widget.get_allocated_width()
            y+=row*widget.get_allocated_height()
        args=['mouse',round(x*scale),round(y*scale)]
        if mode:args.extend([0,mode])
        self.card_command(entry,*args)

    def card_click(self,entry,event,mode):
        if time.monotonic()<getattr(self,'suppress_click_until',0):return True
        if mode=='up' and not self.dragging:self.select(self.entries.index(entry))
        if entry.get('card_hover'):self.card_mouse(entry,event,mode)
        return True

    def hover_details(self,entry,event):
        self.position_overlays(entry)
        x,y,w,h=entry['video_rect']
        show=event.y>=y+h-min(100,h*.25) and x<=event.x<=x+w
        for other in self.entries:
            if other is not entry and other.get('card_hover'):
                self.card_command(other,'script-message','stream-card-hover','no');other['card_hover']=False
        entry['card_hover']=show
        self.update_card(entry)
        self.card_mouse(entry,event)
        self.card_command(entry,'script-message','stream-card-hover','yes' if show else 'no')
        return False

    def rebuild(self):
        # Moving grid attachments preserves GL contexts and already decoded frames.
        retained=[e.get('widget') for e in self.entries]
        for widget in self.grid.get_children():
            if widget not in retained:self.grid.remove(widget)
        for entry,(x,y) in zip(self.entries,self.pane_positions()):
            if 'widget' not in entry:self.grid.attach(self.pane(entry),x,y,1,1)
            else:
                self.grid.child_set_property(entry['widget'],'left-attach',x)
                self.grid.child_set_property(entry['widget'],'top-attach',y)
        self.blank=None
        if len(self.entries)==3:
            blank=Gtk.EventBox();blank.set_no_show_all(True);blank.override_background_color(Gtk.StateFlags.NORMAL,Gdk.RGBA(0,0,0,1));self.grid.attach(blank,1,1,1,1);self.blank=blank
        self.window.show_all();self.arrange();self.last_layout=None;self.select(min(self.selected,len(self.entries)-1));self.tick()

    def arrange(self):
        single=self.zoomed or self.suspended
        # Hide unselected surfaces before moving any cells to the same location.
        for i,entry in enumerate(self.entries):
            if single and i!=self.selected:entry['widget'].hide()
        for i,(entry,(x,y)) in enumerate(zip(self.entries,self.pane_positions())):
            self.grid.child_set_property(entry['widget'],'left-attach',0 if self.zoomed or self.suspended else x)
            self.grid.child_set_property(entry['widget'],'top-attach',0 if self.zoomed or self.suspended else y)
            entry['widget'].set_visible(not (self.zoomed or self.suspended) or i==self.selected)
            if entry.get('video'):
                entry['video'].set('video-align-x',0 if self.zoomed or self.suspended else (1 if x==0 else -1))
                entry['video'].set('video-align-y',0 if self.zoomed or self.suspended or len(self.entries)<3 else (1 if y==0 else -1))
        if self.blank:self.blank.set_visible(not (self.zoomed or self.suspended))

    def set_zoomed(self,zoomed):
        self.zoomed=zoomed
        self.set('user-data/stream-multiview-zoomed',zoomed)
        self.arrange();self.last_layout=None;self.tick()

    def toggle_fullscreen(self):
        subprocess.Popen([str(SCRIPTS/'toggle-pip-fullscreen.sh'),'--pid',str(self.pid)],
            env=dict(os.environ,STREAM_MULTIVIEW_TOGGLE='1'),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    def add(self,row):
        existing=next((i for i,e in enumerate(self.entries) if (e['service'],e['name'].casefold())==(row['service'],row['name'].casefold())),None)
        if existing is not None:self.select(existing);return
        if len(self.entries)>=4:
            self.replace(row);return
        self.zoomed=False;self.set('user-data/stream-multiview-zoomed',False)
        entry=dict(row,ready=False,url='',page=channel(row),started=time.monotonic(),slot=len(self.entries))
        video=Video(lambda:self.loaded(entry),lambda reason:self.stream_ended(entry,reason));entry['video']=video
        video.set('volume',self.original_volume)
        self.entries.append(entry);self.rebuild()
        self.load(entry)

    def load(self,entry):
        generation=entry.get('generation',0)+1;entry['generation']=generation
        entry.update(ready=False,failed=False,started=time.monotonic());self.update_loading(entry)
        name,service,page=entry['name'],entry['service'],entry['page']
        def worker():
            try:
                url=resolve(name,service,page)
                GLib.idle_add(self.resolved,entry,url,generation)
            except Exception:GLib.idle_add(self.failed,entry,generation)
        threading.Thread(target=worker,daemon=True).start()

    def resolved(self,entry,url,generation):
        if not self.closed and entry in self.entries and entry.get('generation')==generation:
            if isinstance(url,dict):entry.update(url)
            else:entry['url']=url
            entry['switching_until']=time.monotonic()+2
            entry['video'].load(entry['url'],entry['service'])
        return False

    def loaded(self,entry):
        if entry not in self.entries:return
        entry['ready']=True;entry['failed']=False;self.update_loading(entry);self.update_card(entry);self.select(self.selected)
        if self.entries[0].get('ended'):self.remove(0)

    def failed(self,entry,generation=None):
        if entry in self.entries and (generation is None or entry.get('generation')==generation):
            if entry.get('video'):entry['video'].command('show-text','Stream unavailable — q to close',5000)
            entry['failed']=True;entry.pop('waiting_native_url',None);self.update_loading(entry)
        return False

    def select(self,index):
        if not self.entries:return True
        self.selected=index
        self.set('user-data/stream-multiview-selected',index)
        for i,entry in enumerate(self.entries):
            chosen=i==index
            context=entry['widget'].get_style_context()
            (context.add_class if chosen else context.remove_class)('selected')
            entry['indicator'].set_visible(chosen)
            if entry['video']:entry['video'].set('mute','no' if chosen else 'yes')
        self.set('mute',index!=0)
        if self.zoomed or self.suspended:self.arrange();self.last_layout=None
        return True

    def adopt(self,entry):
        if entry is self.entries[0]:return
        if not entry.get('url'):return
        if entry.get('context'):
            path=Path.home()/'.cache'/f"{entry['service'].lower()}-live-player.json"
            temporary=path.with_suffix('.multiview.tmp')
            temporary.write_text(json.dumps(entry['context']));temporary.chmod(0o600);temporary.replace(path)
        session=Path('/tmp/twitch-session.id').read_text().strip() if Path('/tmp/twitch-session.id').exists() else ''
        ipc(self.state,'script-message','twitch-load',entry['name'],entry.get('title') or entry['name'],
            entry['url'],'','',entry['service'],session,entry['page'])
        self.entries[0].update({k:entry[k] for k in ('name','service','title','url','page') if k in entry})
        self.entries[0]['ended']=False
        self.entries[0]['generation']=self.entries[0].get('generation',0)+1
        self.entries[0]['switching_until']=time.monotonic()+2

    def remove(self,index):
        self.zoomed=False;self.set('user-data/stream-multiview-zoomed',False)
        if len(self.entries)<=1:self.close_session();return
        if index==0:
            replacement=next((e for e in self.entries[1:] if e.get('ready')),None)
            if not replacement:
                self.entries[0]['ended']=bool(self.get('eof-reached'))
                ipc(self.state,'show-text','Wait for another stream to load, or close its loading pane',2500)
                return
            was_audible=self.entries[self.selected] is replacement
            self.adopt(replacement);index=self.entries.index(replacement)
            if was_audible:self.selected=0
        audible=self.entries[self.selected]
        if audible is self.entries[index]:audible=None
        entry=self.entries.pop(index)
        if entry.get('video'):entry['video'].close()
        for slot,remaining in enumerate(sorted(self.entries,key=lambda e:e.get('slot',0))):remaining['slot']=slot
        self.selected=self.entries.index(audible) if audible in self.entries else min(self.selected,len(self.entries)-1)
        if len(self.entries)==1:
            self.selected=0;self.finish()
        else:self.rebuild()

    def replace(self,row):
        # The usual Enter/click replaces only the selected cell.
        if any((e['service'],e['name'].casefold())==(row['service'],row['name'].casefold()) for e in self.entries):
            self.select(next(i for i,e in enumerate(self.entries) if e['service']==row['service'] and e['name'].casefold()==row['name'].casefold()));return
        entry=self.entries[self.selected]
        if self.selected==0:
            generation=entry.get('generation',0)+1;entry['generation']=generation
            entry.update(ready=False,failed=False,started=time.monotonic());self.update_loading(entry)
            # Resolve asynchronously before touching the current native stream.
            def worker():
                try:
                    data=dict(row,page=channel(row));result=resolve(data['name'],data['service'],data['page'])
                    data.update(result if isinstance(result,dict) else {'url':result})
                    GLib.idle_add(self.replace_primary,data,generation)
                except Exception:GLib.idle_add(self.failed,entry,generation)
            threading.Thread(target=worker,daemon=True).start();return
        entry.update(row,page=channel(row),ready=False,failed=False,started=time.monotonic())
        self.load(entry);self.select(self.selected)

    def replace_primary(self,row,generation=None):
        if not self.closed and (generation is None or self.entries[0].get('generation')==generation):
            self.adopt(row);self.entries[0]['waiting_native_url']=row['url'];self.select(self.selected)
        return False

    def tick(self):
        if self.closed:return False
        try:
            windows=clients();player=next((c for c in windows if c['pid']==self.pid),None)
            if not player:self.finish(restore=False);return False
            monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
            mon=next(m for m in monitors if m['id']==player['monitor'])
            visible=bool(player.get('pinned')) or mon.get('activeWorkspace',{}).get('id')==player.get('workspace',{}).get('id')
            width=mon['width']/mon.get('scale',1);height=mon['height']/mon.get('scale',1)
            fullscreen=bool(self.get('fullscreen'))
            if not fullscreen:
                if not self.suspended:
                    self.suspended=True
                    self.set('user-data/stream-multiview',False)
                    layout=self.get('user-data/media-panel-layout') or {}
                    layout.update(left=0,right=0);self.set('user-data/media-panel-layout',layout)
                    for side in ('left','right','top','bottom'):self.set('video-margin-ratio-'+side,0)
                    for axis,value in self.original_align.items():self.set('video-align-'+axis,value)
                    self.arrange();self.select(self.selected)
                    ipc(self.state,'script-message','stream-card-viewport')
                # Keep the SAME decoder/video and audio. Fit its existing surface
                # to the native window instead of reloading/adopting another feed.
                self.mask_owner(self.selected!=0)
                px,py=player['at'];pw,ph=player['size']
                margins=(px-mon['x'],width-(px-mon['x'])-pw,py-mon['y'],height-(py-mon['y'])-ph)
                for edge,value in zip((Layer.Edge.LEFT,Layer.Edge.RIGHT,Layer.Edge.TOP,Layer.Edge.BOTTOM),margins):
                    Layer.set_margin(self.window,edge,max(0,round(value)))
                self.window.set_visible(visible and self.selected!=0)
                return True
            self.mask_owner(False)
            if self.suspended:
                self.suspended=False;self.set('user-data/stream-multiview',True)
                self.arrange();self.select(self.selected);self.last_layout=None
            for edge in (Layer.Edge.RIGHT,Layer.Edge.TOP,Layer.Edge.BOTTOM):Layer.set_margin(self.window,edge,0)
            layout=self.get('user-data/media-panel-layout') or {}
            left=layout.get('left',0);width=mon['width']/mon.get('scale',1);height=mon['height']/mon.get('scale',1)
            nx,ny=self.pane_positions()[0]
            columns=1 if self.zoomed else 2;rows=2 if len(self.entries)>2 and not self.zoomed else 1
            if self.zoomed:nx=ny=0
            native_left=left+nx*(1-left)/columns
            right=1-(left+(nx+1)*(1-left)/columns)
            top=ny/rows;bottom=1-(ny+1)/rows
            geometry=(left,width,height,bottom,nx,ny,self.zoomed)
            if geometry!=self.last_layout:
                self.last_layout=geometry
                Layer.set_margin(self.window,Layer.Edge.LEFT,round(left*width))
                layout.update(left=left,right=right)
                self.set('user-data/media-panel-layout',layout)
            for key,value in [('left',native_left),('right',right),('bottom',bottom),('top',top)]:
                if abs(float(self.get('video-margin-ratio-'+key) or 0)-value)>.001:self.set('video-margin-ratio-'+key,value)
            for axis,value in [('x',0 if self.zoomed else (1 if nx==0 else -1)),('y',0 if rows==1 else (1 if ny==0 else -1))]:
                if float(self.get('video-align-'+axis) or 0)!=value:self.set('video-align-'+axis,value)
            self.window.set_visible(visible)
            if time.monotonic()-self.metadata_updated>1:
                self.metadata=metadata.load();self.metadata_updated=time.monotonic()
                for entry in self.entries:self.update_card(entry)
            for entry in self.entries:
                self.position_overlays(entry)
            for entry in self.entries:
                if not entry['ready'] and not entry.get('failed') and time.monotonic()-entry['started']>65:self.failed(entry)
        except (OSError,ValueError,StopIteration,subprocess.SubprocessError):pass
        return True

    def player_key(self,key):
        entry=self.entries[self.selected]
        video=entry.get('video')
        menu=video.get('user-data/clip-menu-visible')=='true' if video else self.get('user-data/clip-menu-visible') is True
        # Clip-menu Enter/Escape must win over expanding/restoring a pane.
        if not menu:
            if key in ('j','k','UP','DOWN') and self.get('user-data/stream-sidebar-open'):
                ipc(self.state,'script-message','stream-sidebar-navigate','down' if key in ('j','DOWN') else 'up');return True
            if key=='ENTER':self.set_zoomed(not self.zoomed);return True
            if key=='ESC':self.set_zoomed(False);return True
            if key=='q':self.close_selected();return True
            if key=='f':self.toggle_fullscreen();return True
        if key in ('+','-','_'):
            self.card_command(entry,'add','video-zoom',.1 if key=='+' else -.1)
        else:self.card_command(entry,'keypress',key)
        return True

    def key(self,_,event):
        name=Gdk.keyval_name(event.keyval)
        if event.state&Gdk.ModifierType.CONTROL_MASK and name in ('h','j','k','l'):
            self.move_focus(name);return True
        if name in ('Tab','slash'):
            ipc(self.state,'keypress','TAB' if name=='Tab' else '/');return True
        code=Gdk.keyval_to_unicode(event.keyval)
        key=mpv_key(name,chr(code) if code else '',
                    bool(event.state&Gdk.ModifierType.CONTROL_MASK),bool(event.state&Gdk.ModifierType.MOD1_MASK))
        return self.player_key(key) if key else False

    def close_selected(self):
        # Consult MPV as well as the cached mode: q can arrive during an f transition.
        if self.suspended or not self.get('fullscreen'):self.close_session()
        else:self.remove(self.selected)

    def close_session(self):
        if self.closed:return False
        # Do not adopt another feed or reopen chat while shutting down.
        try:ipc(self.state,'quit')
        except (OSError,ValueError):pass
        return self.finish(restore=False)

    def mask_owner(self,masked):
        if self.owner_masked==masked:return
        self.owner_masked=masked
        # The native window owns geometry and fullscreen transitions. Its old
        # feed must never peek through beneath the selected embedded video.
        self.set('brightness',-100 if masked else self.original_brightness)
        if masked:ipc(self.state,'script-message','stream-card-hover','no')

    def finish(self,windowed=False,restore=True):
        if self.closed:return False
        if restore and self.entries and self.selected:
            self.adopt(self.entries[self.selected])
        self.closed=True;self.endpoint.unlink(missing_ok=True);self.server.close()
        for entry in self.entries:
            if entry.get('video'):entry['video'].close()
        if restore:
            try:
                self.mask_owner(False)
                self.set('keep-open',self.original_keep_open)
                layout=self.get('user-data/media-panel-layout') or {}
                layout.update(right=0)
                self.set('user-data/media-panel-layout',layout)
                self.set('video-margin-ratio-left',float(layout.get('left',0)))
                for side in ('right','bottom','top'):self.set('video-margin-ratio-'+side,0)
                for axis,value in self.original_align.items():self.set('video-align-'+axis,value)
                self.set('user-data/stream-multiview',False);self.set('mute',False)
                self.set('user-data/stream-multiview-zoomed',False)
            except (OSError,ValueError):pass
        if restore:
            try:ipc(self.state,'script-message','stream-card-viewport')
            except (OSError,ValueError):pass
        self.window.destroy()
        if restore and windowed:
            subprocess.Popen([str(SCRIPTS/'toggle-pip-fullscreen.sh'),'--pid',str(self.pid),'--exit'])
        elif restore and self.chat_open:
            subprocess.Popen([sys.executable,str(SCRIPTS/'media-chat.py')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        Gtk.main_quit();return False


if __name__=='__main__':
    pid=int(sys.argv[1]);row=json.loads(sys.argv[2])
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    with (ROOT/f'{pid}.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if send(pid,'add',row=row):sys.exit(0)
        from stream_player_identity import identity
        current=next((c for c in clients() if c['pid']==pid),None)
        if not current or not current.get('fullscreen'):sys.exit(0)
        existing=identity(current)
        if existing and existing[0]==row['service'] and existing[1].casefold()==row['name'].casefold():
            ipc({'player':current,'socket':socket_for(current)},'show-text','This stream is already open',2000)
            sys.exit(0)
        theater=Theater(pid,row)
        fcntl.flock(lock,fcntl.LOCK_UN)
        try:Gtk.main()
        finally:
            if not theater.closed:theater.finish()
