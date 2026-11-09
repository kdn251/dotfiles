import unittest
from stream_sidebar import rows,choice

class SidebarTests(unittest.TestCase):
    def test_idle_focus_restoration_keeps_browsing_separate_from_search(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='restore_input_focus')
        ns={};exec(compile(ast.Module(body=[method],type_ignores=[]),'focus','exec'),ns)
        row=Mock();search=Mock()
        sidebar=SimpleNamespace(closing=False,leaving_fullscreen=False,searching=True,search_editing=False,
                                window=Mock(),list=Mock(),search=search)
        sidebar.window.get_visible.return_value=True
        sidebar.list.get_selected_row.return_value=row
        ns['restore_input_focus'](sidebar)
        row.grab_focus.assert_called_once();search.grab_focus_without_selecting.assert_not_called()
        sidebar.search_editing=True
        ns['restore_input_focus'](sidebar)
        search.grab_focus_without_selecting.assert_called_once()
        sidebar.window.get_visible.return_value=False
        ns['restore_input_focus'](sidebar)
        search.grab_focus_without_selecting.assert_called_once()

    def test_navigation_requires_key_events_even_if_release_is_lost(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace,MethodType
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('stop_navigation','start_navigation','key_released')]
        timers={};intervals=[];moves=[];clock=[1.0]
        def timeout(ms,cb):
            ident=len(intervals)+1;intervals.append(ms);timers[ident]=cb;return ident
        namespace={'GLib':SimpleNamespace(timeout_add=timeout,source_remove=lambda i:timers.pop(i,None)),
                   'Gdk':SimpleNamespace(KEY_j=1,KEY_k=2,KEY_Down=3,KEY_Up=4),
                   'time':SimpleNamespace(monotonic=lambda:clock[0])}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'repeat','exec'),namespace)
        obj=SimpleNamespace(held_nav=None,nav_timer=None,move_selection=moves.append,
                            hide_stream_title=lambda:None,show_stream_title=lambda *a:None,
                            list=SimpleNamespace(get_selected_row=lambda:None))
        for name in ('stop_navigation','start_navigation','key_released'):setattr(obj,name,MethodType(namespace[name],obj))
        obj.start_navigation(1)
        for _ in range(20):obj.start_navigation(1)
        self.assertEqual(moves,[1])
        self.assertEqual(intervals,[250])
        clock[0]+=.1;obj.start_navigation(1)
        self.assertEqual(moves,[1,1])
        # Simulate a missing key release and an arbitrarily late timer callback.
        clock[0]+=10
        self.assertFalse(timers[2]())
        self.assertEqual(moves,[1,1])
        self.assertIsNone(obj.held_nav)
        obj.start_navigation(1)
        obj.key_released(None,2,0,0)
        self.assertEqual(obj.held_nav,1)
        obj.key_released(None,1,0,0)
        self.assertIsNone(obj.held_nav)
        self.assertNotIn(3,timers)

    def test_fullscreen_exit_does_not_run_chat_cleanup_on_keyboard_thread(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        key=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='key')
        names={n.attr:n.attr for n in ast.walk(key) if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name) and n.value.id=='Gdk'}
        launch=Mock();ipc=Mock()
        namespace={'Gdk':SimpleNamespace(**names),'subprocess':SimpleNamespace(Popen=launch,DEVNULL=-3),
                   'SCRIPTS':Path('/scripts'),'socket_for':lambda _: 'socket','ipc':ipc}
        exec(compile(ast.Module(body=[key],type_ignores=[]),'sidebar-key','exec'),namespace)
        sidebar=SimpleNamespace(searching=False,pending_g=0,player={'pid':123},pid=123)
        self.assertTrue(namespace['key'](sidebar,None,'KEY_f',0,0))
        self.assertTrue(sidebar.leaving_fullscreen)
        self.assertEqual(launch.call_args.args[0],['/scripts/toggle-pip-fullscreen.sh','--pid','123','--exit'])
        ipc.assert_not_called()

    def test_old_player_events_cannot_control_replacement(self):
        import ast
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import Mock
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        names=('exited_for_player','retarget_for_player','action_for_player','fullscreen_for_player')
        methods=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in names]
        namespace={}
        exec(compile(ast.Module(body=methods,type_ignores=[]),'sidebar-events','exec'),namespace)
        sidebar=SimpleNamespace(pid=22,player_exited=Mock(),retarget=Mock(),remote_key=Mock(),fullscreen_changed=Mock())
        for method,callback,args in [('exited_for_player','player_exited',()),
                ('retarget_for_player','retarget',({'pid':33},)),
                ('action_for_player','remote_key',('close',)),
                ('fullscreen_for_player','fullscreen_changed',(False,))]:
            namespace[method](sidebar,11,*args)
            getattr(sidebar,callback).assert_not_called()
            namespace[method](sidebar,22,*args)
            getattr(sidebar,callback).assert_called_once()

    def test_collapsed_preference_persists_and_tolerates_invalid_state(self):
        import os,tempfile
        from unittest.mock import patch
        from stream_sidebar import load_collapsed,save_collapsed,sidebar_preferences_path
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_STATE_HOME=folder):
            self.assertFalse(load_collapsed())
            save_collapsed(True)
            self.assertTrue(load_collapsed())
            save_collapsed(False)
            self.assertFalse(load_collapsed())
            for invalid in ('broken','[]','{"collapsed":"false"}'):
                sidebar_preferences_path().write_text(invalid)
                self.assertFalse(load_collapsed())

    def test_slash_opens_search_without_sidebar_and_toggles_existing_search(self):
        import subprocess,tempfile
        from pathlib import Path
        script=Path(__file__).resolve().parents[2]/'mpv/.config/mpv/scripts/stream-sidebar.lua'
        harness="""
package.preload['mp.utils']=function()return {getpid=function()return 42 end}end
local props={fullscreen=true,['user-data/stream-service']='Twitch'}
local bindings,observers={},{}
local launched
local launches=0
mp={get_property_native=function(k,d)if props[k]==nil then return d end return props[k]end,
get_property_bool=function(k,d)if props[k]==nil then return d end return props[k]end,
set_property_native=function(k,v)props[k]=v end,
register_script_message=function()end,
remove_key_binding=function(k)bindings[k]=nil end,
add_forced_key_binding=function(k,n,f)bindings[n]={key=k,fn=f}end,
observe_property=function(k,t,f)observers[k]=f;f(k,props[k])end,
command_native_async=function(cmd,cb)launched=cmd;launches=launches+1 end,osd_message=function()end}
dofile(arg[1])
local tab=bindings['stream-live-sidebar'].fn
tab({event='down'});tab({event='repeat'})
assert(launches==0,'Tab must finish before the sidebar takes keyboard focus')
tab({event='up'})
assert(launches==1)
tab({event='up'})
assert(launches==1,'An inherited release must not reopen the sidebar')
tab({event='down'});tab({event='up',canceled=true})
assert(launches==1)
assert(bindings['stream-live-search'].key=='/')
bindings['stream-live-search'].fn()
assert(launched.args[4]=='--search')
props['user-data/stream-sidebar-open']=true
props['user-data/media-panel-layout']={left=.1}
observers['user-data/media-panel-layout'](nil,props['user-data/media-panel-layout'])
bindings['stream-live-search'].fn()
assert(props['user-data/stream-sidebar-action'].action=='search')
props.fullscreen=false;observers.fullscreen(nil,false)
assert(bindings['stream-live-search']==nil)
print('Sidebar search shortcut checks passed')
"""
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'check.lua';path.write_text(harness)
            subprocess.run(['lua',str(path),str(script)],check=True,capture_output=True)

    def test_windowed_restore_pins_once_and_never_unpins(self):
        import json,os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        from stream_sidebar import restore_windowed
        player=dict(pid=123,address='0x123',at=[100,200],size=[640,360],pinned=False)
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
            (Path(folder)/f"pip-fullscreen-{os.getuid()}-0x123.geometry.return").write_text(json.dumps(player))
            for pinned,fullscreen,expected in ((False,0,1),(True,0,0),(False,2,0)):
                with self.subTest(pinned=pinned,fullscreen=fullscreen),patch('subprocess.check_output',return_value=json.dumps([dict(player,pinned=pinned,fullscreen=fullscreen)])),patch('subprocess.run') as run:
                    restore_windowed(player)
                    self.assertEqual(sum('window.pin' in call.args[0][-1] for call in run.call_args_list),expected)

    def test_native_workspaces_without_numeric_ids(self):
        from stream_sidebar import visible_on_workspace
        monitor={'activeWorkspace':{'name':'1'},'specialWorkspace':{'name':''}}
        player={'workspace':{'name':'1'}}
        self.assertTrue(visible_on_workspace(player,monitor))
        self.assertFalse(visible_on_workspace({'workspace':{'name':'special:stream_staging'}},monitor))
        monitor['specialWorkspace']={'name':'special:chatterino_chat'}
        self.assertTrue(visible_on_workspace(player,monitor))
        monitor['specialWorkspace']={'name':'special:scratch'}
        self.assertFalse(visible_on_workspace(player,monitor))
        special_player={'workspace':{'name':'special:magic'}}
        monitor['specialWorkspace']={'name':'special:magic'}
        self.assertTrue(visible_on_workspace(special_player,monitor))
        monitor['specialWorkspace']={'name':''}
        self.assertFalse(visible_on_workspace(special_player,monitor))
        monitor['specialWorkspace']={'name':'special:scratch'}
        self.assertFalse(visible_on_workspace(special_player,monitor))
        self.assertFalse(visible_on_workspace({'workspace':{}},monitor))

    def test_search_ranks_names_before_category_and_title(self):
        from stream_sidebar import search_rows
        catalog=[dict(name='other',category='Gaming',title='Watching soda'),
                 dict(name='third',category='Soda games',title=''),
                 dict(name='sodapoppin',category='',title=''),
                 dict(name='soda',category='',title='')]
        self.assertEqual([r['name'] for r in search_rows(catalog,'SoDa')],['soda','sodapoppin','third','other'])
        self.assertEqual(search_rows(catalog,''),catalog)
        self.assertEqual(search_rows(catalog,'missing'),[])

    def test_live_counts_order_and_service_identity(self):
        cache={'t':{'a':{'checked_at':1000,'viewer_count':100}},
               'k':{'b':{'checked_at':1000,'viewer_count':200}},
               'y':{'c':{'checked_at':1000,'viewer_count':None}},
               'r':{'old':{'checked_at':1,'viewer_count':10000}}}
        result=rows(cache,now=1001)
        self.assertEqual([r['name'] for r in result],['b','a','c'])
        self.assertEqual(choice(result[0]),'b (Kick)')
        self.assertEqual(choice(result[1]),'a')
        self.assertIsNone(result[2]['viewers'])


    def test_panels_fit_together_and_restore_in_either_order(self):
        from media_panel_layout import FIT,PROPERTY,update
        import tempfile,os
        from unittest.mock import patch
        for first in ('left','right'):
            second='right' if first=='left' else 'left'
            for close_first in ('left','right'):
                with self.subTest(first=first,close_first=close_first), tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
                    props=dict(FIT,panscan=1,**{'video-zoom':.15})
                    original=dict(props)
                    def command(op,key,value=None):
                        if op=='get_property':return props.get(key)
                        props[key]=value
                    update(command,123,first,.2)
                    update(command,123,second,.25)
                    self.assertGreater(props['video-margin-ratio-left'],0)
                    self.assertGreater(props['video-margin-ratio-right'],0)
                    self.assertEqual(props['panscan'],0)
                    self.assertEqual(props['video-zoom'],0)
                    update(command,123,close_first,0)
                    remaining='right' if close_first=='left' else 'left'
                    self.assertEqual(props['video-margin-ratio-'+close_first],0)
                    self.assertGreater(props['video-margin-ratio-'+remaining],0)
                    self.assertEqual(props['panscan'],0)
                    update(command,123,remaining,0)
                    self.assertEqual({k:props[k] for k in original},original)
                    self.assertEqual(props[PROPERTY],{})

    def test_sidebar_restores_fractional_margin_exactly(self):
        from stream_sidebar import VideoSpace
        from media_panel_layout import FIT
        import tempfile,os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
            props=dict(FIT)
            def command(op,key,value=None):
                if op=='get_property':return props.get(key)
                props[key]=round(value,6) if isinstance(value,float) else value
            space=VideoSpace(command,123)
            space.reserve(320,1440)
            self.assertEqual(props['video-margin-ratio-left'],.222222)
            space.restore()
            self.assertEqual(props['video-margin-ratio-left'],0)

    def test_current_stream_is_first_even_with_fewer_viewers(self):
        cache={'t':{'small':{'checked_at':1000,'viewer_count':10},
                    'big':{'checked_at':1000,'viewer_count':50000}},
               'k':{'small':{'checked_at':1000,'viewer_count':100000}}}
        result=rows(cache,now=1001,current=('Twitch','Small'))
        self.assertEqual([(r['name'],r['service']) for r in result],
                         [('small','Twitch'),('small','Kick'),('big','Twitch')])

    def test_reopen_does_not_restore_sidebar_margin_from_chat_snapshot(self):
        from media_panel_layout import FIT,PROPERTY,update
        import tempfile,os
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
            props=dict(FIT)
            def command(op,key,value=None):
                if op=='get_property':return props.get(key)
                props[key]=value
            stale=dict(FIT,**{'video-margin-ratio-left':.159722})
            for _ in range(3):
                update(command,123,'left',.159722,stale)
                update(command,123,'right',.2,stale)
                update(command,123,'left',0)
                update(command,123,'right',0,stale)
                self.assertEqual(props['video-margin-ratio-left'],0)
                self.assertEqual(props['video-margin-ratio-right'],0)
                self.assertEqual(props[PROPERTY],{})
            update(command,123,'right',0,stale)
            self.assertEqual(props['video-margin-ratio-left'],0)

    def test_switch_transfers_only_an_open_sidebar(self):
        import json
        import stream_sidebar
        from unittest.mock import patch
        player={'class':'mpv','pid':123}
        for opened in (True,False):
            with self.subTest(opened=opened), \
                    patch('subprocess.check_output',return_value=json.dumps([player]).encode()), \
                    patch('media_chat_fullscreen.socket_for',return_value='/tmp/test.sock'), \
                    patch('media_chat_fullscreen.ipc',return_value=opened), \
                    patch('subprocess.Popen') as launch:
                stream_sidebar.prepare_transfer('session','Kick','example')
                self.assertEqual(launch.call_count,int(opened))
                if opened:self.assertEqual(launch.call_args.args[0][-4:],['session','Kick','example','123'])

    def test_transfer_cancels_if_sidebar_was_explicitly_closed(self):
        import json
        from stream_sidebar import transfer
        from unittest.mock import patch
        player={'class':'mpv','pid':123,'fullscreen':2}
        with patch('pathlib.Path.read_text',return_value='session'), \
                patch('subprocess.check_output',return_value=json.dumps([player]).encode()), \
                patch('media_chat_fullscreen.socket_for',return_value='/tmp/test.sock'), \
                patch('media_chat_fullscreen.ipc',return_value=False), \
                patch('subprocess.Popen') as launch:
            transfer('session','Kick','example',123)
            launch.assert_not_called()
