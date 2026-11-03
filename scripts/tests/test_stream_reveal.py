import json
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
import media_chat_fullscreen as chat

class RevealTests(TestCase):
    def test_hidden_stream_moves_to_focused_workspace_and_repins_only_itself(self):
        old=dict(pid=42,address='stream',**{'class':'mpv'},monitor=0,pinned=False,
                 workspace=dict(id=-9,name='special:mpvhidden'))
        shown=dict(old,workspace=dict(id=3,name='3'))
        calls=[];reads=[]
        def hypr(*args):
            calls.append(args)
            if args==('-j','clients'):
                reads.append(True);return json.dumps([old if len(reads)==1 else shown])
            if args==('-j','monitors'):
                return json.dumps([dict(id=0,focused=False,activeWorkspace=dict(id=1)),
                                   dict(id=1,focused=True,activeWorkspace=dict(id=3))])
            return ''
        with tempfile.TemporaryDirectory() as directory,patch.object(chat,'ROOT',Path(directory)),patch.object(chat,'hypr',side_effect=hypr):
            saved=Path(directory)/'pip-hidden-pinned';saved.write_text('stream\nother-window\n')
            chat.reveal_player(42)
            self.assertIn(('dispatch','movetoworkspacesilent','3,address:stream'),calls)
            self.assertIn(('dispatch','pin','address:stream'),calls)
            self.assertEqual(saved.read_text(),'other-window\n')

    def test_visible_stream_keeps_its_layout(self):
        with patch.object(chat,'hypr',return_value=json.dumps([dict(pid=42,**{'class':'mpv'},workspace=dict(name='1'))])) as hypr:
            chat.reveal_player(42)
            hypr.assert_called_once_with('-j','clients')
