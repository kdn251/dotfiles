#!/usr/bin/env python3
"""Fullscreen live-channel sidebar, opened by Tab in the managed MPV player."""
import ctypes
import fcntl
import json
import os
from pathlib import Path
import subprocess
import signal
import threading
import time
import socket
import sys
os.environ.setdefault('GSK_RENDERER','gl')
ctypes.CDLL('libgtk4-layer-shell.so',mode=ctypes.RTLD_GLOBAL)
import gi
gi.require_version('Gtk','4.0')
gi.require_version('Gdk','4.0')
gi.require_version('Gtk4LayerShell','1.0')
from gi.repository import Gtk,Gdk,Gio,GLib,Pango,Gsk,Graphene,Gtk4LayerShell as Layer
from stream_sidebar import rows,choice,VideoSpace,restore_windowed,visible_on_workspace,search_rows
from stream_menu_metadata import highlight
from media_chat_fullscreen import ipc,socket_for,read as chat_layout
from mpv_clip import Player
from stream_player_identity import identity
SCRIPTS=Path(__file__).resolve().parent

def clients():
    return json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','clients'],timeout=1))

class Avatar(Gtk.Image):
    def do_snapshot(self,snapshot):
        clip=Gsk.RoundedRect()
        clip.init_from_rect(Graphene.Rect().init(0,0,self.get_width(),self.get_height()),22)
        snapshot.push_rounded_clip(clip)
        Gtk.Image.do_snapshot(self,snapshot)
        snapshot.pop()

class Sidebar(Gtk.Application):
    def __init__(self,pid):
        super().__init__(application_id='local.stream.sidebar',flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.pid=pid
        self.video_space=None
        self.connection=None
        self.events=None
        self.workspace_events=None
        self.closing=False
        self.leaving_fullscreen=False
        self.dead=False
        self.pidfd=None
        self.pid_watch=None
        self.handoff_until=0
        self.searching=False
        self.connect('shutdown',self.release_video)
        self.connect('shutdown',self.stop_events)
        self.connect('activate',self.activate_sidebar)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGTERM,self.dismiss)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGUSR1,self.dismiss)
    def activate_sidebar(self,_):
        player=next((c for c in clients() if c.get('pid')==self.pid and c.get('fullscreen')),None)
        if not player:self.quit();return
        self.player=player
        try:
            self.pidfd=os.pidfd_open(self.pid)
            self.pid_watch=GLib.io_add_watch(self.pidfd,GLib.IO_IN,self.player_exited)
        except ProcessLookupError:self.quit();return
        self.current=identity(player)
        self.window=Gtk.ApplicationWindow(application=self,title='Live channels')
        Layer.init_for_window(self.window)
        Layer.set_namespace(self.window,'stream-sidebar')
        Layer.set_layer(self.window,Layer.Layer.OVERLAY)
        Layer.set_exclusive_zone(self.window,-1)  # Fullscreen edges, including the Waybar area.
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.EXCLUSIVE)
        for edge in (Layer.Edge.LEFT,Layer.Edge.TOP,Layer.Edge.BOTTOM):Layer.set_anchor(self.window,edge,True)
        monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
        monitor=next((m for m in monitors if m['id']==player['monitor']),None)
        display=Gdk.Display.get_default()
        if monitor:
            for m in display.get_monitors():
                if m.get_connector()==monitor['name']:Layer.set_monitor(self.window,m);break
        self.window.set_default_size(230,-1)
        self.monitor=monitor
        endpoint=socket_for(player)
        if endpoint:
            self.connection=Player(endpoint,self.pid)
            self.connection.socket.settimeout(.4)
            self.connection.command("set_property","user-data/stream-sidebar-open",True)
            self.start_events(endpoint)
            existing=chat_layout()
            fallback=existing.get('properties') if existing and existing.get('player',{}).get('pid')==self.pid else None
            self.video_space=VideoSpace(self.connection.command,self.pid,fallback)
            self.window.connect('map',lambda *_:GLib.idle_add(self.reserve_video))
        css=Gtk.CssProvider()
        css.load_from_data(b"""
        window {background:#1f1f23;color:#efeff1;font-family:sans-serif;}
        .heading {font-size:16px;font-weight:700;padding:18px 10px;}
        .collapse {background:transparent;color:#efeff1;border:none;box-shadow:none;padding:6px;min-width:20px;min-height:20px;}
        .collapse:hover {background:#3a3a40;}
        .hint {color:#adadb8;font-size:12px;padding:10px;}
        entry.sidebar-search {background:#303038;color:#efeff1;border:1px solid #484850;
            border-radius:6px;box-shadow:none;outline:none;min-height:30px;
            padding:4px 8px;font-size:14px;}
        entry.sidebar-search:focus-within {border-color:#a970ff;box-shadow:none;outline:none;}
        entry.sidebar-search image {color:#adadb8;margin-right:6px;}
        entry.sidebar-search text {background:transparent;color:#efeff1;}
        entry.sidebar-search selection {background:#664795;color:#ffffff;}
        list {background:transparent;}
        row {padding:10px 10px;border-radius:0;margin:0;}
        row label {color:#efeff1;}
        row:selected {background:#3a3a40;}
        row:hover {background:#303038;}
        .name {color:#f7f7f8;font-weight:700;font-size:16px;}
        .category {color:#c4c4cc;font-size:14px;}
        .viewers {color:#ff6269;font-size:14px;font-weight:600;}
        popover.stream-title > contents {background:#26262c;color:#efeff1;border:1px solid #484850;border-radius:6px;}
        popover.stream-title label {font-size:14px;}
        .playing {color:#cfadff;}
        row.current {border-left:3px solid #a970ff;padding-left:7px;}
        """)
        Gtk.StyleContext.add_provider_for_display(display,css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        header=Gtk.Box(spacing=0)
        title=Gtk.Label(label='LIVE CHANNELS',xalign=0,hexpand=True)
        title.add_css_class('heading');header.append(title)
        collapse=Gtk.Button.new_from_icon_name('pan-start-symbolic')
        collapse.add_css_class('collapse');collapse.set_valign(Gtk.Align.CENTER)
        collapse.set_margin_end(8)
        collapse.set_tooltip_text('Collapse live channels (Tab)')
        collapse.connect('clicked',self.dismiss)
        search_button=Gtk.Button.new_from_icon_name('system-search-symbolic')
        search_button.add_css_class('collapse');search_button.set_tooltip_text('Search live channels (/)')
        search_button.connect('clicked',lambda *_:self.open_search())
        header.append(search_button);header.append(collapse);box.append(header)
        self.search=Gtk.Entry(placeholder_text='Search channels…')
        self.search.add_css_class('sidebar-search')
        self.search.set_width_chars(1)
        self.search.set_icon_from_icon_name(Gtk.EntryIconPosition.PRIMARY,'system-search-symbolic')
        self.search.set_margin_start(8);self.search.set_margin_end(8);self.search.set_margin_bottom(8)
        self.search.set_visible(False)
        self.search.connect('changed',self.search_changed)
        box.append(self.search)
        self.collapse=collapse
        self.list=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.set_activate_on_single_click(True)
        self.list.connect('row-activated',self.choose)
        self.title_popup=None
        self.list.connect('row-selected',self.show_stream_title)
        scroll=Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.EXTERNAL)
        scroll.set_child(self.list);box.append(scroll)
        self.scroll=scroll
        hint=Gtk.Label(label='/ Search · j/k · Enter to watch · Tab to close')
        hint.add_css_class('hint');hint.set_wrap(True);hint.set_max_width_chars(28);box.append(hint)
        self.window.set_child(box)
        keys=Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed',self.key);self.window.add_controller(keys)
        self.catalog=None
        self.refresh()
        GLib.timeout_add(200,self.check_player)
        GLib.timeout_add_seconds(5,self.refresh)
        self.window.present()
        self.list.grab_focus()
        self.start_workspace_events()
    def start_workspace_events(self):
        # React immediately; polling remains a fallback if the compositor reconnects.
        path=Path(os.environ.get("XDG_RUNTIME_DIR","/tmp"))/"hypr"/os.environ.get("HYPRLAND_INSTANCE_SIGNATURE","")/".socket2.sock"
        listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:listener.connect(str(path))
        except OSError:
            listener.close();return
        self.workspace_events=listener
        def listen():
            try:
                with listener.makefile("r") as stream:
                    for line in stream:
                        if line.split(">>",1)[0] in ("workspace","workspacev2","focusedmon","movewindow","movewindowv2","fullscreen","activespecial"):
                            GLib.idle_add(self.workspace_changed)
            except (OSError,ValueError):pass
        threading.Thread(target=listen,daemon=True).start()
    def workspace_changed(self):
        self.check_player()
        return False
    def start_events(self,endpoint):
        self.events=Player(endpoint,self.pid)
        self.events.socket.settimeout(None)
        previous=self.events.get('user-data/stream-sidebar-action')
        self.events.command('observe_property',701,'user-data/stream-sidebar-action')
        self.events.command('observe_property',702,'fullscreen')
        self.events.command('observe_property',703,'user-data/stream-sidebar-replacement')
        events=self.events
        watched_pid=self.pid
        def listen():
            nonlocal previous
            try:
                for line in events.stream:
                    event=json.loads(line)
                    if watched_pid!=self.pid:return
                    if event.get('event')=='shutdown':
                        GLib.idle_add(self.player_exited);return
                    if event.get('event')!='property-change':continue
                    if event.get('name')=='user-data/stream-sidebar-replacement' and isinstance(event.get('data'),dict):
                        GLib.idle_add(self.retarget,event['data'])
                    if event.get('name')=='fullscreen':
                        GLib.idle_add(self.fullscreen_for_player,watched_pid,event.get('data'))
                    if event.get('name')=='user-data/stream-sidebar-action':
                        data=event.get('data')
                        if isinstance(data,dict) and data!=previous:
                            previous=data
                            GLib.idle_add(self.remote_key,data.get('action'))
            except (OSError,ValueError):pass
        threading.Thread(target=listen,daemon=True).start()
    def fullscreen_for_player(self,pid,fullscreen):
        if pid==self.pid:self.fullscreen_changed(fullscreen)
        return False
    def retarget(self,data):
        if self.closing or data.get('pid')==self.pid:return False
        new_pid=data.get('pid')
        if not isinstance(new_pid,int):return False
        player=next((c for c in clients() if c.get('pid')==new_pid),None)
        if not player:return False
        endpoint=socket_for(player)
        if not endpoint:return False
        try:
            connection=Player(endpoint,new_pid)
            connection.socket.settimeout(.4)
            connection.command('set_property','user-data/stream-sidebar-open',True)
            pidfd=os.pidfd_open(new_pid)
        except (OSError,ValueError):return False
        old_connection=self.connection
        old_events=self.events
        print(f'sidebar retarget {self.pid} -> {new_pid}',file=sys.stderr,flush=True)
        self.pid=new_pid;self.player=player;self.connection=connection
        self.handoff_until=time.monotonic()+3
        if self.pid_watch:GLib.source_remove(self.pid_watch)
        if self.pidfd is not None:os.close(self.pidfd)
        self.pidfd=pidfd
        self.pid_watch=GLib.io_add_watch(pidfd,GLib.IO_IN,self.player_exited)
        if old_events:
            try:old_events.socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            old_events.close()
        self.start_events(endpoint)
        self.video_space=VideoSpace(connection.command,new_pid)
        self.reserve_video()
        if old_connection:
            try:old_connection.command('set_property','user-data/stream-sidebar-attached',new_pid)
            except (OSError,ValueError):pass
            old_connection.close()
        self.current=identity(player) or self.current
        self.refresh()
        return False
    def fullscreen_changed(self,fullscreen):
        if self.closing:return False
        if fullscreen is False:
            if time.monotonic()>=self.handoff_until:self.suspend_fullscreen()
        else:
            self.leaving_fullscreen=False
            self.check_player()
        return False
    def suspend_fullscreen(self):
        # Keep the menu and its selection alive, but give the windowed video
        # all its space back. Remapping on fullscreen restores the left margin.
        self.window.set_visible(False)
        if self.video_space:self.video_space.restore()
    def remote_key(self,action):
        if action=='search':self.open_search()
        elif action=='close':self.dismiss()
        elif action=='choose':self.choose(self.list,self.list.get_selected_row())
        elif action in ('up','down'):
            self.key(None,Gdk.KEY_j if action=='down' else Gdk.KEY_k,0,0)
        return False
    def stop_events(self,*_):
        self.closing=True
        if self.workspace_events:
            try:self.workspace_events.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.workspace_events.close();self.workspace_events=None
        if self.events:
            try:self.events.socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
            self.events.close();self.events=None
    def reserve_video(self):
        if self.video_space and self.monitor:
            dimension='height' if self.monitor.get('transform',0)%2 else 'width'
            width=self.monitor[dimension]/self.monitor.get('scale',1)
            try:self.video_space.reserve(self.window.get_width() or 230,width)
            except (OSError,ValueError):self.quit()
        return False
    def dismiss(self,*_):
        self.closing=True
        if self.connection:
            try:self.connection.command("set_property","user-data/stream-sidebar-open",False)
            except (OSError,ValueError):pass
        # Unmap immediately; restore before returning focus to the video.
        if hasattr(self,'window'):self.window.set_visible(False)
        self.release_video()
        self.quit()
        return False
    def player_exited(self,*_):
        self.closing=True
        self.dead=True
        if hasattr(self,'window'):self.window.set_visible(False)
        self.quit()
        return False
    def release_video(self,*_):
        if self.video_space and not self.dead:self.video_space.restore()
        if self.connection:
            self.connection.close();self.connection=None
        if self.pid_watch:
            GLib.source_remove(self.pid_watch);self.pid_watch=None
        if self.pidfd is not None:
            os.close(self.pidfd);self.pidfd=None
    def open_search(self):
        self.searching=True
        self.search.set_visible(True)
        # Search may arrive through MPV while the video owns keyboard focus.
        Layer.set_keyboard_mode(self.window,Layer.KeyboardMode.EXCLUSIVE)
        self.window.present()
        self.search.grab_focus_without_selecting()
    def search_changed(self,*_):
        self.catalog=None
        self.refresh()
        self.list.select_row(self.list.get_row_at_index(0))
    def move_selection(self,step):
        if not self.catalog:return
        current=self.list.get_selected_row()
        index=((current.get_index() if current else 0)+step)%len(self.catalog)
        row=self.list.get_row_at_index(index)
        self.list.select_row(row)
        if self.searching:
            # Scroll to the selected row while leaving typing focus in the field.
            row.grab_focus();self.search.grab_focus_without_selecting()
        else:row.grab_focus()
    def hide_stream_title(self,*_):
        if self.title_popup:
            self.title_popup.popdown()
            self.title_popup.unparent()
            self.title_popup=None
    def show_stream_title(self,_,row):
        self.hide_stream_title()
        if not row or not hasattr(row,'data') or not row.data.get('title'):return
        popup=Gtk.Popover()
        popup.add_css_class('stream-title')
        popup.set_has_arrow(False)
        popup.set_autohide(False)
        popup.set_focusable(False)
        popup.set_can_focus(False)
        popup.set_position(Gtk.PositionType.RIGHT)
        label=Gtk.Label(label=row.data['title'],xalign=0)
        label.set_wrap(True)
        label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        label.set_max_width_chars(42)
        label.set_margin_top(8);label.set_margin_bottom(8)
        label.set_margin_start(10);label.set_margin_end(10)
        popup.set_child(label)
        popup.set_parent(row)
        self.title_popup=popup
        if row.get_mapped():popup.popup()
    def refresh(self):
        try:self.current=identity(self.player) or self.current
        except (OSError,ValueError):pass
        query=self.search.get_text() if self.searching else ""
        catalog=search_rows(rows(current=self.current),query)
        if catalog==self.catalog:return True
        focused=self.window.get_focus() is not None
        selected=self.list.get_selected_row()
        selected_key=choice(selected.data) if selected and hasattr(selected,'data') else None
        self.catalog=catalog
        self.hide_stream_title()
        while child:=self.list.get_first_child():self.list.remove(child)
        preferred=None
        for data in catalog:
            row=Gtk.ListBoxRow();row.data=data
            body=Gtk.Box(spacing=8)
            image=Avatar();image.set_size_request(32,32);image.set_pixel_size(32)
            if Path(data['icon']).is_file():image.set_from_file(data['icon'])
            else:image.set_from_icon_name('avatar-default-symbolic')
            body.append(image)
            labels=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3,hexpand=True)
            current=self.current and self.current[0]==data['service'] and self.current[1].casefold()==data['name'].casefold()
            name=Gtk.Label(xalign=0);name.set_markup(highlight(data['name'],query,fuzzy=True));name.add_css_class('name')
            if current:
                name.add_css_class('playing');row.add_css_class('current')
            name.set_ellipsize(Pango.EllipsizeMode.END);name.set_max_width_chars(17);name.set_width_chars(1)
            labels.append(name)
            subtitle=data['category'] or data['service']
            if query and query.casefold() in data['title'].casefold() and query.casefold() not in subtitle.casefold():subtitle=data['title']
            category=Gtk.Label(xalign=0);category.set_markup(highlight(subtitle,query))
            category.add_css_class('category');category.set_ellipsize(Pango.EllipsizeMode.END);category.set_max_width_chars(21);category.set_width_chars(1)
            labels.append(category);body.append(labels)
            count=data['viewers']
            count='—' if count is None else (f'{count/1000:.1f}k' if count>=1000 else str(int(count)))
            live=Gtk.Label(label='● '+count);live.add_css_class('viewers');body.append(live)
            row.set_child(body)
            motion=Gtk.EventControllerMotion()
            motion.connect('enter',lambda controller,x,y,r=row:self.show_stream_title(None,r))
            motion.connect('leave',lambda *_:self.show_stream_title(None,self.list.get_selected_row()))
            row.add_controller(motion)
            self.list.append(row)
            if choice(data)==selected_key or (selected_key is None and current):preferred=row
        if not catalog:
            empty=Gtk.Label(label='No matching live channels' if query else 'No live channels in the current cache',wrap=True)
            self.list.append(empty)
        selected=preferred or self.list.get_row_at_index(0)
        self.list.select_row(selected)
        # Rebuilding removes the focused GtkListBoxRow. Selection alone does
        # not install a keyboard target, leaving the exclusive layer eating F.
        if focused and self.window.get_visible():
            if not self.searching:(selected or self.list).grab_focus()
        return True
    def check_player(self):
        if self.closing:return False
        try:
            player=next((c for c in clients() if c.get('pid')==self.pid),None)
            if not player:
                self.dismiss();return False
            self.player=player
            # The replacement is briefly fullscreen in its hidden staging
            # workspace. Keep the existing sidebar/focus until it is revealed.
            if time.monotonic()<self.handoff_until and player.get('workspace',{}).get('name')=='special:stream_staging':return True
            if not player.get('fullscreen'):
                if time.monotonic()<self.handoff_until:return True
                if self.leaving_fullscreen:restore_windowed(player)
                self.leaving_fullscreen=False
                self.suspend_fullscreen();return True
            if self.leaving_fullscreen:return True
            self.handoff_until=0
            monitors=json.loads(subprocess.check_output(['/usr/bin/hyprctl','-j','monitors'],timeout=1))
            monitor=next((m for m in monitors if m['id']==player['monitor']),None)
            # A layer-shell surface has no workspace of its own. Unmap it while
            # away, retaining the widgets, selection and reserved video space.
            visible=visible_on_workspace(player,monitor)
            if visible and not self.window.get_visible():
                self.reserve_video()
                self.window.present()
                if self.searching:self.search.grab_focus_without_selecting()
                else:self.list.grab_focus()
            elif not visible and self.window.get_visible():
                self.window.set_visible(False)
        except (OSError,ValueError,subprocess.SubprocessError):
            # A temporary compositor query failure should not close the list.
            pass
        return True
    def choose(self,_,row):
        self.hide_stream_title()
        if self.searching:self.search.grab_focus_without_selecting()
        if not row or not hasattr(row,'data'):return
        data=row.data
        if not (self.current and self.current[0]==data['service'] and self.current[1].casefold()==data['name'].casefold()):
            subprocess.Popen([str(SCRIPTS/'twitch-launcher.sh'),choice(data)],
                             env=dict(os.environ,STREAM_SWITCH_SOURCE_PID=str(self.pid)),stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
            if self.searching:
                self.searching=False
                self.search.set_visible(False)
                self.search.set_text('')
                self.list.grab_focus()
    def key(self,_,key,code,modifiers):
        if self.searching:
            if key==Gdk.KEY_Escape:
                if self.search.get_text():self.search.set_text('')
                else:
                    self.searching=False;self.search.set_visible(False);self.list.grab_focus()
                return True
            if key in (Gdk.KEY_Up,Gdk.KEY_Down):
                self.move_selection(1 if key==Gdk.KEY_Down else -1);return True
            if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):
                self.choose(self.list,self.list.get_selected_row());return True
            if key in (Gdk.KEY_Tab,Gdk.KEY_ISO_Left_Tab):self.dismiss();return True
            return False
        if key in (Gdk.KEY_less,Gdk.KEY_greater):
            try:
                ipc({'socket':socket_for(self.player),'player':self.player},
                    'keypress','<' if key==Gdk.KEY_less else '>')
            except (OSError,ValueError):pass
            return True
        if key==Gdk.KEY_slash:
            self.open_search();return True
        if key in (Gdk.KEY_Tab,Gdk.KEY_ISO_Left_Tab,Gdk.KEY_Escape):
            self.dismiss();return True
        if key in (Gdk.KEY_q,Gdk.KEY_f):
            try:
                state={'socket':socket_for(self.player),'player':self.player}
                if key==Gdk.KEY_f:
                    # Forwarding a synthetic F starts an asynchronous compositor
                    # toggle while this layer still owns focus. Address MPV's
                    # fullscreen property directly and wait for its actual exit.
                    self.leaving_fullscreen=True
                    ipc(state,'set_property','fullscreen',False)
                    self.suspend_fullscreen()
                else:
                    self.release_video()
                    ipc(state,'quit')
            except (OSError,ValueError):
                self.leaving_fullscreen=False
            if key==Gdk.KEY_q:self.dismiss()
            return True
        if key in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):
            self.choose(self.list,self.list.get_selected_row());return True
        if key in (Gdk.KEY_j,Gdk.KEY_Down,Gdk.KEY_k,Gdk.KEY_Up):
            self.move_selection(1 if key in (Gdk.KEY_j,Gdk.KEY_Down) else -1)
            return True
        return False

if __name__=='__main__':
    log=Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'stream-sidebar.log'
    log.touch(mode=0o600,exist_ok=True)
    sys.stderr=log.open('a',buffering=1)
    print(f'{time.time():.3f} sidebar started for player {sys.argv[1]}',file=sys.stderr)
    with (Path(os.environ.get('XDG_RUNTIME_DIR','/tmp'))/'stream-sidebar.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            lock.seek(0)
            try:os.kill(int(lock.read()),signal.SIGUSR1)
            except (ProcessLookupError,ValueError):pass
            sys.exit(0)
        lock.seek(0);lock.truncate();lock.write(str(os.getpid()));lock.flush()
        sys.exit(Sidebar(int(sys.argv[1])).run([sys.argv[0]]))
