import ast
import sys
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from stream_multiview import typed_stream,neighbor,cells,channel

class TheaterTests(unittest.TestCase):
    def theater_method(self,name):
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-multiview.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Theater')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
        namespace={}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'theater-method','exec'),namespace)
        return namespace[name]

    def test_enter_toggles_expansion_and_escape_always_restores_grid(self):
        obj=SimpleNamespace(zoomed=False,entries=[{'video':None}],selected=0,get=Mock(return_value=False),card_command=Mock())
        player_key=self.theater_method('player_key')
        obj.player_key=lambda key:player_key(obj,key)
        obj.set_zoomed=lambda value:setattr(obj,'zoomed',value)
        action=self.theater_method('action')
        action(obj,{'action':'zoom'});self.assertTrue(obj.zoomed)
        action(obj,{'action':'zoom'});self.assertFalse(obj.zoomed)
        action(obj,{'action':'zoom'});action(obj,{'action':'grid'});self.assertFalse(obj.zoomed)

    def test_indicator_and_audio_selection_survive_windowed_mode(self):
        entries=[dict(widget=Mock(),indicator=Mock(),video=None if i==0 else Mock()) for i in range(4)]
        obj=SimpleNamespace(entries=entries,suspended=False,zoomed=False,set=Mock(),arrange=Mock())
        select=self.theater_method('select');select(obj,2)
        for i,entry in enumerate(entries):entry['indicator'].set_visible.assert_called_with(i==2)
        entries[1]['video'].set.assert_called_with('mute','yes')
        entries[2]['video'].set.assert_called_with('mute','no')
        entries[3]['video'].set.assert_called_with('mute','yes')
        obj.set.assert_called_with('mute',True)
        obj.suspended=True;select(obj,2)
        for i,entry in enumerate(entries[1:],1):entry['video'].set.assert_called_with('mute','no' if i==2 else 'yes')
        obj.set.assert_called_with('mute',True)

    def test_windowed_layout_shows_only_selected_without_changing_zoom_preference(self):
        entries=[dict(widget=Mock(),video=None if i==0 else Mock()) for i in range(4)]
        obj=SimpleNamespace(entries=entries,suspended=True,zoomed=False,selected=2,grid=Mock(),blank=None)
        arrange=self.theater_method('arrange')
        arrange.__globals__['cells']=cells
        arrange(obj)
        for i,entry in enumerate(entries):entry['widget'].set_visible.assert_called_with(i==2)
        entries[2]['video'].set.assert_any_call('video-align-x',0)
        entries[2]['video'].set.assert_any_call('video-align-y',0)
        obj.suspended=False;arrange(obj)
        for entry in entries:entry['widget'].set_visible.assert_called_with(True)
        self.assertEqual(obj.selected,2)
        self.assertFalse(obj.zoomed)

    def test_each_added_player_receives_its_own_card_identity(self):
        import stream_menu_metadata as metadata
        update=self.theater_method('update_card');update.__globals__['metadata']=metadata
        obj=SimpleNamespace(metadata={'t':{'alice':{'title':'First title','viewer_count':123}},
                                      'k':{'bob':{'title':'Second title','viewer_count':456}}})
        for name,service,title in [('Alice','Twitch','First title'),('Bob','Kick','Second title')]:
            video=Mock();entry=dict(video=video,name=name,service=service,page='https://example.com')
            update(obj,entry)
            video.set.assert_any_call('user-data/stream-name',name)
            video.set.assert_any_call('user-data/stream-service',service)
            self.assertIn(title,entry['card_properties']['force-media-title'])

    @unittest.skipUnless(os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY'),'display required')
    def test_player_initializes_after_gtk_sets_user_numeric_locale(self):
        code='''
import locale,time,json
from stream_multiview_video import Video,Gtk
Gtk.init([])
locale.setlocale(locale.LC_NUMERIC,'en_US.utf8')
player=Video(lambda:None)
assert locale.setlocale(locale.LC_NUMERIC)=='C'
for _ in range(100):
 if player.get('user-data/osc/visibility'):break
 time.sleep(.02)
assert json.loads(player.get('user-data/osc/visibility'))=='auto', 'Shared OSC did not initialize'
bindings=json.loads(player.get('input-bindings'))
commands=[b.get('cmd','') for b in bindings]
assert any('clip_menu/open' in cmd for cmd in commands)
assert any('screenshot_copy/save-and-copy' in cmd for cmd in commands)
from mpv_clip import Player
import os
peer=Player(str(player.endpoint),os.getpid())
assert peer.get('input-ipc-server')==str(player.endpoint)
peer.close()
player.close()
time.sleep(.1)
assert not player.endpoint.exists()

'''
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]/'scripts'),LC_ALL='en_US.utf8')
        result=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_fifth_stream_replaces_focused_pane_without_adding_a_player(self):
        entries=[dict(name=str(i),service='Twitch') for i in range(4)]
        obj=SimpleNamespace(entries=entries,selected=2,replace=Mock(),select=Mock())
        add=self.theater_method('add')
        row=dict(name='New streamer',service='Kick')
        add(obj,row)
        obj.replace.assert_called_once_with(row)
        self.assertEqual(len(entries),4)
        self.assertEqual(obj.selected,2)
        obj.replace.reset_mock()
        add(obj,dict(name='1',service='Twitch'))
        obj.select.assert_called_once_with(1)
        obj.replace.assert_not_called()

    def test_sidebar_enter_adds_to_active_multiview(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='choose')
        namespace={}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'sidebar-choose','exec'),namespace)
        obj=SimpleNamespace(stop_navigation=Mock(),hide_stream_title=Mock(),searching=False,
                            pid=123,stop_hover_preview=Mock())
        row=SimpleNamespace(data=dict(name='New streamer',service='Kick'))
        with patch('stream_multiview.send',return_value=True) as send:
            namespace['choose'](obj,None,row)
            send.assert_called_once_with(123,'add',row=row.data)
        obj.stop_hover_preview.assert_called_once()

    def test_windowed_close_quits_entire_session_fullscreen_close_removes_one(self):
        close=self.theater_method('close_selected')
        obj=SimpleNamespace(suspended=True,get=Mock(return_value=False),selected=2,
                            close_session=Mock(),remove=Mock())
        close(obj);obj.close_session.assert_called_once();obj.remove.assert_not_called()
        obj.suspended=False;obj.get.return_value=True
        close(obj);obj.remove.assert_called_once_with(2)
        obj.get.return_value=False;obj.close_session.reset_mock()
        close(obj);obj.close_session.assert_called_once()

    def test_quit_session_never_adopts_or_restores_another_feed(self):
        close=self.theater_method('close_session');command=Mock()
        close.__globals__['ipc']=command
        obj=SimpleNamespace(closed=False,state={},finish=Mock(return_value=False))
        close(obj)
        command.assert_called_once_with({},'quit')
        obj.finish.assert_called_once_with(restore=False)

    def test_info_card_anchors_to_pane_bottom_including_letterbox(self):
        position=self.theater_method('position_overlays');position.__globals__['cells']=cells
        entries=[]
        for i in range(4):
            widget=Mock();widget.get_allocated_width.return_value=720;widget.get_allocated_height.return_value=480
            video=None if i==0 else Mock()
            if video:video.get.return_value='1.7777778'
            entries.append(dict(widget=widget,video=video,indicator=Mock(),aspect=16/9))
        window=Mock();window.get_allocated_height.return_value=960
        obj=SimpleNamespace(window=window,entries=entries,zoomed=False,suspended=False,card_command=Mock(),get=Mock(return_value={'left':0}))
        for e in entries:position(obj,e)
        self.assertEqual(entries[0]['card_viewport'][1]+entries[0]['card_viewport'][3],.5)
        for e in entries[1:]:
            self.assertEqual(e['card_viewport'][1]+e['card_viewport'][3],1)
            self.assertEqual(e['card_viewport'][4],2)
        self.assertEqual(entries[0]['card_viewport'][4],1)

    def test_shortcuts_reach_selected_pane_and_clip_menu_owns_enter_escape(self):
        key=self.theater_method('player_key')
        video=Mock();video.get.return_value='false'
        entries=[{'video':None},{'video':video}]
        obj=SimpleNamespace(entries=entries,selected=1,get=Mock(return_value=False),
                            card_command=Mock(),set_zoomed=Mock(),zoomed=True)
        for value in ('S','C','Ctrl+c','SPACE'):
            key(obj,value);obj.card_command.assert_called_with(entries[1],'keypress',value)
        key(obj,'+');obj.card_command.assert_called_with(entries[1],'add','video-zoom',.1)
        key(obj,'-');obj.card_command.assert_called_with(entries[1],'add','video-zoom',-.1)
        video.get.return_value='true'
        for value in ('ENTER','ESC','j','k'):
            key(obj,value);obj.card_command.assert_called_with(entries[1],'keypress',value)
        obj.set_zoomed.assert_not_called()

    def test_navigation_reaches_open_sidebar_even_when_video_surface_has_focus(self):
        key=self.theater_method('player_key');command=Mock();key.__globals__['ipc']=command
        video=Mock();video.get.return_value='false'
        obj=SimpleNamespace(entries=[{'video':video}],selected=0,get=Mock(return_value=True),state={},card_command=Mock())
        for value in ('j','k','UP','DOWN'):
            key(obj,value);command.assert_called_with({},'script-message','stream-sidebar-navigate','down' if value in ('j','DOWN') else 'up')
        obj.card_command.assert_not_called()

    def test_shifted_playback_keys_keep_their_identity(self):
        from stream_multiview import mpv_key
        self.assertEqual(mpv_key('S','S'),'S')
        self.assertEqual(mpv_key('C','C'),'C')
        self.assertEqual(mpv_key('plus','+'),'+')
        self.assertEqual(mpv_key('c','c',control=True),'Ctrl+c')
        self.assertEqual(mpv_key('Return'),'ENTER')

    def test_embedded_osc_uses_shared_sizing_settings(self):
        import tempfile
        from stream_multiview_video import shared_osc_options
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'osc.conf'
            path.write_text('# Scale both modes\nscalefullscreen=1.5\nscalewindowed = 1.25 # window\nvidscale=yes\nlayout=bottombar\n')
            self.assertEqual(shared_osc_options(path),'osc-scalefullscreen=1.5,osc-scalewindowed=1.25,osc-vidscale=yes')
            self.assertEqual(shared_osc_options(Path(folder)/'missing'),'')

    def test_directional_navigation_two_three_four(self):
        self.assertEqual(neighbor(2,0,'l'),1)
        self.assertEqual(neighbor(2,1,'h'),0)
        self.assertEqual(neighbor(3,0,'j'),2)
        self.assertEqual(neighbor(3,1,'j'),1)
        self.assertEqual(neighbor(4,1,'j'),3)
        self.assertEqual(neighbor(4,3,'h'),2)
        self.assertEqual(neighbor(4,2,'k'),0)
        self.assertEqual(len(set(cells(4))),4)

    def test_platform_prefixes(self):
        for prefix,service in [('k','Kick'),('r','Rumble'),('y','YouTube'),('t','Twitch')]:
            self.assertEqual(typed_stream(prefix+'/SomePerson')['service'],service)
        self.assertEqual(typed_stream('y/@someone')['name'],'someone')
        for invalid in ['k/','k/foo/bar','x/person','just text','k/$(bad)']:
            self.assertIsNone(typed_stream(invalid))

    def test_saved_channel_names_accept_space_separated_files(self):
        with patch.object(Path,'read_text',return_value='FriendlyName https://www.youtube.com/@actualhandle\n'):
            self.assertEqual(channel({'name':'friendlyname','service':'YouTube'}),'https://www.youtube.com/@actualhandle')

    def test_prefixed_search_limits_platform(self):
        from stream_sidebar import search_rows
        catalog=[dict(name='same',service=s,category='',title='') for s in ('Twitch','Kick','YouTube')]
        self.assertEqual([r['service'] for r in search_rows(catalog,'k/sa')],['Kick'])
        self.assertEqual([r['service'] for r in search_rows(catalog,'y/')],['YouTube'])

    def test_typed_unknown_stream_launches_without_matching_row(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='choose')
        import os
        process=Mock()
        namespace={'subprocess':process,'os':os,'SCRIPTS':Path('/scripts')}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'sidebar-choose','exec'),namespace)
        obj=SimpleNamespace(stop_navigation=Mock(),hide_stream_title=Mock(),searching=True,
            search=Mock(),current=('Twitch','existing'),pid=123,hover_preview=None,
            stop_hover_preview=Mock(),list=Mock())
        obj.search.get_text.return_value='k/unlisted_person'
        with patch('stream_multiview.send',return_value=False):namespace['choose'](obj,None,None)
        self.assertEqual(process.Popen.call_args.args[0],['/scripts/twitch-launcher.sh','k/unlisted_person'])

    def test_slash_inside_query_is_not_a_toggle(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='key')
        class Keys:
            def __getattr__(self,name):return name
        namespace={'Gdk':Keys()}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'sidebar-key','exec'),namespace)
        sidebar=SimpleNamespace(searching=True,search_editing=True,pending_g=0,
            search=Mock(),open_search=Mock())
        sidebar.search.get_text.return_value='k'
        self.assertFalse(namespace['key'](sidebar,None,'KEY_slash',0,0))
        sidebar.open_search.assert_not_called()
        sidebar.search.get_text.return_value=''
        self.assertTrue(namespace['key'](sidebar,None,'KEY_slash',0,0))
        sidebar.open_search.assert_called_once()

    def test_control_navigation_routes_to_theater(self):
        source=ast.parse((Path(__file__).resolve().parents[1]/'scripts/stream-sidebar.py').read_text())
        cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Sidebar')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='key')
        keys=SimpleNamespace(ModifierType=SimpleNamespace(CONTROL_MASK=4),KEY_h=104,KEY_j=106,KEY_k=107,KEY_l=108)
        namespace={'Gdk':keys}
        exec(compile(ast.Module(body=[method],type_ignores=[]),'sidebar-key','exec'),namespace)
        with patch('stream_multiview.send',return_value=True) as send:
            self.assertTrue(namespace['key'](SimpleNamespace(pid=123),None,108,0,4))
            send.assert_called_once_with(123,'move',direction='l')

if __name__=='__main__':unittest.main()
