import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from media_chat_live import live_target,valid_chat_url
from test_media_chat import chat

class LiveChatTests(unittest.TestCase):
    def test_routes_each_running_service_and_rejects_stale_context(self):
        urls={'kick':'https://kick.com/popout/jandro/chat',
              'rumble':'https://rumble.com/chat/popup/123456',
              'youtube':'https://www.youtube.com/live_chat?v=abc123DEF45&is_popout=1'}
        for service,url in urls.items():
            with self.subTest(service=service),tempfile.TemporaryDirectory() as d:
                root=Path(d);(root/'.cache').mkdir()
                (root/'.cache'/f'{service}-live-player.json').write_text(json.dumps({'chat_url':url}))
                args=f'mpv\0--input-ipc-server=/tmp/mpv-{service}-live-ipc\0'.encode()
                clients=[{'class':'mpv','pid':123,'address':'live'},{'class':'mpv','pid':124,'address':'other'}]
                def cmdline(path):return args if '/123/' in str(path) else b'mpv\0'
                with patch.object(Path,'home',return_value=root),patch.object(Path,'read_bytes',cmdline):
                    target=live_target(clients,'live')
                    self.assertEqual(target['url'],url)
                    if service=='youtube':self.assertEqual(target['title'],'YouTube live chat')
                    self.assertIsNone(live_target(clients,'other'))
    def test_popout_url_validation(self):
        for url in ['file:///etc/passwd','https://kick.com.evil/popout/test/chat','https://rumble.com/chat/popup/bad','https://youtube.com/watch?v=abc123DEF45']:
            self.assertFalse(valid_chat_url(url))
    def test_switch_to_live_hides_comments_and_twitch(self):
        live=dict(url='https://kick.com/popout/jandro/chat',title='Kick live chat',service='kick')
        clients=[{'class':chat.CLASS,'address':'comments'},{'class':'com.chatterino.chatterino','address':'twitch'}]
        def respond(*args):
            if args==('-j','clients'):return json.dumps(clients+[{'class':chat.LIVE_CLASS,'address':'live'}])
            if args==('-j','activewindow'):return '{}'
            if args==('-j','monitors'):return json.dumps([{'focused':True,'specialWorkspace':{'name':'special:'+chat.WORKSPACE}}])
            return 'ok'
        with tempfile.TemporaryDirectory() as d,patch.object(chat,'STATE',Path(d)/'state'),patch.object(chat,'live_target',return_value=live),patch.object(chat,'hypr',side_effect=respond) as hypr,patch.object(chat.subprocess,'Popen') as spawn:
            chat.main()
            for addr in ('comments','twitch'):
                hypr.assert_any_call('dispatch','movetoworkspacesilent','special:media_chat_closing,address:'+addr)
                hypr.assert_any_call('dispatch','closewindow','address:'+addr)
            self.assertEqual(spawn.call_args.args[0][-2:],[live['url'],live['title']])
    def test_toggle_existing_live_panel(self):
        live=dict(url='https://kick.com/popout/jandro/chat',title='Kick live chat',service='kick')
        with tempfile.TemporaryDirectory() as d:
            state=Path(d)/'state';state.write_text(json.dumps(live))
            with patch.object(chat,'STATE',state),patch.object(chat,'live_target',return_value=live),patch.object(chat,'hypr',side_effect=[json.dumps([{'class':chat.LIVE_CLASS,'address':'live'}]),'{}','ok']) as hypr,patch.object(chat.subprocess,'Popen') as spawn:
                chat.main();spawn.assert_not_called()
                hypr.assert_called_with('dispatch','togglespecialworkspace',chat.WORKSPACE)
