#!/usr/bin/env python3
"""Live agent list and explicit, identity-checked terminal navigation."""
import argparse,json,pathlib,subprocess,sys,time
import attention
from activity import PATH
from activity_probe import process_identity

def snapshot():
    try:
        data=json.loads(PATH.read_text())
        if time.time()-data.get('updated',0)>8:return {'agents':[],'unavailable':['Activity monitor'],'stale':True}
        return data
    except (OSError,ValueError):return {'agents':[],'unavailable':['Activity monitor'],'stale':True}

def target_for(row,clients):
    if row.get('background'):return None
    if row.get('remote'):
        if row['agent'] not in ('Claude','Codex') or not row['remote'].get('terminal'):return None
        return attention.resolve_target({'remote':row['remote']},clients)
    proc=row.get('process') or {}
    if row['host']!='local':
        if not proc.get('connection'):return None
        return attention.resolve_target({'ssh_route':{'host':row['host'],'connection':proc['connection']}},clients)
    if row['agent']=='Codex':
        return attention.resolve_target({'name':row.get('name')},clients)
    if proc.get('pid'):
        try:
            if process_identity(proc['pid'])[1]!=proc.get('start'):return None
            return attention.process_target(proc['pid'],proc.get('kitty_id')) or None
        except (OSError,ValueError):return None
    return None

def focus_row(host,agent,sid):
    data=snapshot()
    row=next((r for r in data['agents'] if (r['host'],r['agent'],r['id'])==(host,agent,sid)),None)
    if row is None:raise RuntimeError('That session is no longer available. Reopen the agent list.')
    target=target_for(row,attention.hypr('clients'))
    if not target:raise RuntimeError('No matching terminal is available for this session.')
    active=attention.hypr('activewindow')
    if 'moonlight' in active.get('class','').lower() and active.get('title')!='Moonlight':
        config=attention.config();profile=config.get('games',{}).get(config.get('active_game'))
        if not profile:raise RuntimeError('Select a game profile before switching from Moonlight.')
        ok,detail=attention.pause_game(profile,active)
        if not ok:raise RuntimeError('Could not confirm the game paused: '+detail)
    attention.focus(target)

def age(timestamp):
    if not timestamp:return None
    seconds=max(0,int(time.time()-timestamp))
    return f'{seconds//3600}h {(seconds%3600)//60}m' if seconds>=3600 else f'{seconds//60}m {seconds%60}s' if seconds>=60 else f'{seconds}s'

def panel():
    import gi
    gi.require_version('Gtk','3.0');gi.require_version('GtkLayerShell','0.1')
    from gi.repository import Gtk,Gdk,GLib,GtkLayerShell,Pango,GdkPixbuf
    class AgentIcon(Gtk.DrawingArea):
        frames={}
        def __init__(self,agent,working):
            super().__init__()
            self.agent=agent;self.working=working
            asset='codex.png' if agent=='Codex' else 'claude.svg'
            self.pixbuf=GdkPixbuf.Pixbuf.new_from_file_at_scale(str(attention.BASE/asset),48,48,True)
            if self.working and agent not in AgentIcon.frames:
                sheet=GdkPixbuf.Pixbuf.new_from_file(str(attention.BASE/(agent.lower()+'-working.png')))
                AgentIcon.frames[agent]=[sheet.new_subpixbuf(0,y,48,48) for y in range(0,sheet.get_height(),48)]
            self.set_size_request(24,24)
            self.connect('draw',self.draw_icon)
            self.tick=self.add_tick_callback(self.animate) if self.working else None
        def animate(self,*args):
            self.queue_draw();return True
        def draw_icon(self,widget,cr):
            frames=AgentIcon.frames.get(self.agent,[])
            pixbuf=frames[int(time.monotonic()*30)%len(frames)] if self.working else self.pixbuf
            cr.translate(self.get_allocated_width()/2,self.get_allocated_height()/2)
            size=24 if self.agent=='Codex' else 20
            cr.scale(size/pixbuf.get_width(),size/pixbuf.get_height())
            Gdk.cairo_set_source_pixbuf(cr,pixbuf,-pixbuf.get_width()/2,-pixbuf.get_height()/2)
            cr.paint()
    class App(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='local.agentattention.Panel')
            self.window=None;self.backdrop=None;self.timer=None;self.signature=None
        def do_activate(self):
            if self.window:self.window.destroy();return
            css=Gtk.CssProvider();css.load_from_data(b"""
            window { background: rgba(48,61,72,0.98); background-image: none; opacity: 1; color: #e6edf2; border: 1px solid #819fa8; border-radius: 5px; }
            window.backdrop { background: transparent; border: none; box-shadow: none; }
            .heading { font-size: 12px; color: #aeb8ca; }
            button { background: transparent; border: none; border-radius: 6px; padding: 7px 9px; color: #e5e9f0; box-shadow: none; }
            button:hover { background: rgba(109,143,157,.22); } button:disabled { color: #8c96a7; }
            .name { font-size: 12px; }
            button.inactive .name { color: #aab5bd; }
            """)
            Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
            # A transparent input surface dismisses the panel on any outside click.
            self.backdrop=Gtk.ApplicationWindow(application=self)
            self.backdrop.get_style_context().add_class('backdrop')
            self.backdrop.set_visual(self.backdrop.get_screen().get_rgba_visual())
            GtkLayerShell.init_for_window(self.backdrop)
            GtkLayerShell.set_namespace(self.backdrop,'agent-activity-dismiss')
            GtkLayerShell.set_layer(self.backdrop,GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_exclusive_zone(self.backdrop,-1)
            for edge in (GtkLayerShell.Edge.TOP,GtkLayerShell.Edge.BOTTOM,GtkLayerShell.Edge.LEFT,GtkLayerShell.Edge.RIGHT):
                GtkLayerShell.set_anchor(self.backdrop,edge,True)
            outside=Gtk.EventBox();outside.set_visible_window(False)
            outside.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
            outside.connect('button-press-event',lambda *args:self.window.destroy() if self.window else None)
            self.backdrop.add(outside);self.backdrop.show_all()
            self.window=Gtk.ApplicationWindow(application=self);self.window.set_title('Agent activity')
            self.window.set_visual(self.window.get_screen().get_rgba_visual())
            self.window.set_resizable(False)
            GtkLayerShell.init_for_window(self.window);GtkLayerShell.set_namespace(self.window,'agent-activity-panel')
            GtkLayerShell.set_layer(self.window,GtkLayerShell.Layer.OVERLAY)
            for edge in (GtkLayerShell.Edge.TOP,GtkLayerShell.Edge.RIGHT):GtkLayerShell.set_anchor(self.window,edge,True)
            GtkLayerShell.set_margin(self.window,GtkLayerShell.Edge.TOP,4);GtkLayerShell.set_margin(self.window,GtkLayerShell.Edge.RIGHT,16)
            GtkLayerShell.set_keyboard_mode(self.window,GtkLayerShell.KeyboardMode.ON_DEMAND)
            self.window.connect('key-press-event',lambda w,e:self.window.destroy() if e.keyval==Gdk.KEY_Escape else False)
            self.window.connect('destroy',self.closed)
            box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3);box.set_border_width(7);self.window.add(box)
            scroll=Gtk.ScrolledWindow();scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.set_max_content_height(300);scroll.set_propagate_natural_height(True);scroll.set_propagate_natural_width(True)
            box.pack_start(scroll,True,True,0);self.rows=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=2);scroll.add(self.rows)
            self.refresh();self.window.show_all();self.timer=GLib.timeout_add_seconds(2,self.refresh)
        def closed(self,*args):
            if self.timer:GLib.source_remove(self.timer);self.timer=None
            self.window=None
            if self.backdrop:self.backdrop.destroy();self.backdrop=None
            self.quit()
        def refresh(self):
            data=snapshot();agents=data.get('agents',[])
            missing=data.get('unavailable',[])

            try:clients=attention.hypr('clients')
            except Exception:clients=[]
            shown=[]
            for row in agents:
                try:available=target_for(row,clients) is not None
                except Exception:available=False
                if row['state']=='idle' and not available:continue
                shown.append((row,available))
            signature=json.dumps([{k:v for k,v in a.items() if k not in ('activity','started')} for a,available in shown],sort_keys=True)+str([v for a,v in shown])+str(missing)
            if signature==self.signature:return True
            self.signature=signature
            for child in self.rows.get_children():child.destroy()
            order={'attention':0,'working':1,'unknown':2,'idle':3}
            for row,available in sorted(shown,key=lambda item:(order.get(item[0]['state'],2),item[0]['host'],item[0].get('name') or '')):
                button=Gtk.Button();button.set_sensitive(available)
                if row['state']!='working':button.get_style_context().add_class('inactive')
                line=Gtk.Box(spacing=9);button.add(line)
                image=AgentIcon(row['agent'],row['state']=='working') if row['agent'] in ('Codex','Claude') else Gtk.Label(label='◆')
                if row['state']!='working':image.set_opacity(.6)
                image.set_tooltip_text(row['agent']);line.pack_start(image,False,False,0)
                name=Gtk.Label(label=row.get('name') or 'Untitled chat',xalign=0);name.get_style_context().add_class('name');name.set_ellipsize(Pango.EllipsizeMode.END);name.set_max_width_chars(30)
                line.pack_start(name,True,True,0)
                status={'working':'Working','attention':'Needs attention','unknown':'Status unknown','idle':'Idle'}.get(row['state'],'Unknown')
                tip=f"{row['agent']} · {row.get('model') or 'model not reported'}\n{row['host']} · {status}"
                if row.get('background'):tip+='\nBackground job · no terminal'
                elif not available:tip+='\nMatching tab unavailable'
                button.set_tooltip_text(tip);button.connect('clicked',self.select,row);self.rows.pack_start(button,False,False,0)
            if missing:self.rows.pack_start(Gtk.Label(label='Status unavailable: '+', '.join(missing)),False,False,4)
            if not shown:self.rows.pack_start(Gtk.Label(label='No active or visible agent sessions'),False,False,8)
            self.rows.show_all();return True
        def select(self,button,row):
            self.window.destroy()
            subprocess.Popen([sys.executable,str(pathlib.Path(__file__).resolve()),'--focus',row['host'],row['agent'],row['id']],start_new_session=True)
    App().run([sys.argv[0]])

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--focus',nargs=3);args=parser.parse_args()
    if args.focus:
        try:focus_row(*args.focus)
        except Exception as exc:attention.notify('Agent navigation',str(exc))
    else:panel()
if __name__=='__main__':main()
