"""Stateful handoffs across platforms, fullscreen modes and both panel states."""
import copy,itertools,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import stream_preview as preview
from media_panel_layout import FIT,PROPERTY,update

class HandoffMatrixTests(unittest.TestCase):
    def test_platform_panel_and_fullscreen_matrix(self):
        services=('Twitch','YouTube','Kick','Rumble')
        for source,destination,fullscreen,left,right,lagged in itertools.product(services,services,(False,True),(False,True),(False,True),(False,True)):
            with self.subTest(source=source,destination=destination,fullscreen=fullscreen,list=left,chat=right),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);session=root/'session';session.write_text('selected')
                old=dict(pid=101,address='old',monitor=0,at=[40,50],size=[547,308],workspace={'name':'1','id':1},fullscreen=2 if (fullscreen != lagged) else 0,**{'class':'mpv'})
                new=dict(pid=202,address='new',monitor=0,at=[0,0],size=[480,270],workspace={'name':'special:stream_staging','id':-1},fullscreen=0,mapped=True,**{'class':'stream-staging'})
                handoff=root/'handoff';handoff.write_text(json.dumps(dict(name='next',service=destination,pid=202,endpoint='new',created=preview.time.time(),staged=True,source_pid=101)))
                props={101:dict(FIT,volume=65,fullscreen=(fullscreen != lagged),**{'user-data/stream-service':source,'user-data/stream-sidebar-open':left}),202:dict(FIT,**{'user-data/preview-ready':True})}
                trace=[]
                class Player:
                    def __init__(self,endpoint,pid):self.pid=pid
                    def get(self,key,default=None):return copy.deepcopy(props[self.pid].get(key,default))
                    def command(self,op,key,*args):
                        if op=='get_property':return self.get(key)
                        if op=='set_property':
                            props[self.pid][key]=copy.deepcopy(args[0])
                            if self.pid==101 and key=='user-data/stream-sidebar-replacement':
                                props[101]['user-data/stream-sidebar-attached']=202
                                props[202]['user-data/stream-sidebar-open']=True
                                trace.append('list attached')
                            if self.pid==202 and key=='options/wayland-app-id':new['class']=args[0]
                            if self.pid==202 and key=='fullscreen':new['fullscreen']=2 if args[0] else 0
                        if op=='script-message' and key=='preview-promote':trace.append('new audible')
                    def close(self):pass
                oldipc=Player('old',101);newipc=Player('new',202)
                (root/'switch.json').write_text(json.dumps(dict(session='selected',pid=101,fullscreen=fullscreen,window=old)))
                with patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
                    if fullscreen and left:update(oldipc.command,101,'left',.16)
                    if fullscreen and right:update(oldipc.command,101,'right',.2)
                    def retire(player):
                        self.assertEqual(player['pid'],101)
                        self.assertIn('new audible',trace)
                        if fullscreen:self.assertEqual(new['fullscreen'],2)
                        trace.append('old removed')
                        if fullscreen and lagged:
                            new['fullscreen']=0
                            props[202]['fullscreen']=False
                    with patch.object(preview,'ROOT',root),patch.object(preview,'HANDOFF',handoff),patch.object(preview,'SESSION',session),patch.object(preview,'CANONICAL',root/'canonical'), \
                            patch.object(preview,'Player',Player),patch.object(preview,'clients',return_value=[old,new]), \
                            patch('media_chat_fullscreen.socket_for',return_value='old'),patch('media_chat_fullscreen.place_player'), \
                            patch('pip_geometry.settings',return_value=([12]*4,1)),patch.object(preview,'retire_player',side_effect=retire), \
                            patch.object(preview.subprocess,'run') as dispatch,patch.object(preview.subprocess,'check_output',return_value=json.dumps([dict(id=0,x=0,y=0,width=1440,height=960,scale=1)])):
                        self.assertEqual(preview.adopt('next','Next','','%s'%destination,'selected','page'),202)
                    if fullscreen:
                        batches=[c.args[0][-1] for c in dispatch.call_args_list if '--batch' in c.args[0]]
                        swap=next(b for b in batches if 'special:stream_retired,address:old' in b)
                        self.assertIn('movetoworkspacesilent 1,address:new',swap)
                        self.assertLess(swap.index('special:stream_retired'),swap.index('1,address:new'))
                    self.assertEqual(trace[-2:],['new audible','old removed'])
                    self.assertEqual(new['fullscreen'],2 if fullscreen else 0)
                    if left:self.assertLess(trace.index('list attached'),trace.index('new audible'))
                    self.assertEqual(props[202]['video-margin-ratio-left'],.16 if fullscreen and left else 0)
                    self.assertEqual(props[202]['video-margin-ratio-right'],.2 if fullscreen and right else 0)
                    # Closing chat must retain the list, then leaving fullscreen
                    # must remove all reservations. Reopening works independently.
                    update(newipc.command,202,'right',0)
                    self.assertEqual(props[202]['video-margin-ratio-left'],.16 if fullscreen and left else 0)
                    update(newipc.command,202,'left',0)
                    self.assertEqual(props[202]['video-margin-ratio-left'],0)
                    self.assertEqual(props[202]['video-margin-ratio-right'],0)
                    update(newipc.command,202,'left',.16);update(newipc.command,202,'right',.2)
                    update(newipc.command,202,'left',0)
                    self.assertEqual(props[202]['video-margin-ratio-right'],.2)
