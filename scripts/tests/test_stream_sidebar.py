import unittest
from stream_sidebar import rows,choice

class SidebarTests(unittest.TestCase):
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
