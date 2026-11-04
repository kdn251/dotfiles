import unittest
from unittest.mock import Mock,patch
import stream_quality_switch as quality

class QualitySwitchTests(unittest.TestCase):
    def player(self,changed=False):
        p=Mock()
        before=[{'type':'video','id':1},{'type':'audio','id':1},
                {'type':'video','id':2,'external':True,'title':'Stream quality: old'}]
        added=[{'type':'video','id':3,'external':True},{'type':'audio','id':3,'external':True}]
        track_reads=iter([before,before+added])
        sessions=iter(['original','changed' if changed else 'original'])
        def get(key,default=None):
            if key=='track-list':return next(track_reads)
            if key=='user-data/stream-ready-session':return next(sessions)
            return {'path':'https://example/playing','rebase-start-time':False,'vid':2}.get(key,default)
        p.get.side_effect=get
        return p

    def test_switch_never_reloads_or_modifies_audio_playback(self):
        player=self.player()
        with patch.object(quality,'Player',return_value=player):
            quality.switch('socket','https://example/new','720p')
        calls=[call.args for call in player.command.call_args_list]
        self.assertIn(('video-add','https://example/new','auto','Stream quality: 720p'),calls)
        self.assertIn(('set_property','vid',3),calls)
        self.assertIn(('audio-remove',3),calls)
        self.assertIn(('video-remove',2),calls)
        self.assertFalse(any(c[0]=='loadfile' for c in calls))
        self.assertFalse(any(c[0]=='set_property' and c[1] in ('aid','pause','mute','volume') for c in calls))
        player.close.assert_called_once()

    def test_stream_changed_during_prepare_does_not_select_old_video(self):
        player=self.player(changed=True)
        with patch.object(quality,'Player',return_value=player),self.assertRaisesRegex(ValueError,'Stream changed'):
            quality.switch('socket','https://example/new','720p')
        self.assertFalse(any(c.args[:2]==('set_property','vid') for c in player.command.call_args_list))

    def test_failure_loading_new_video_leaves_old_audio_and_video(self):
        player=self.player()
        def command(*args):
            if args[0]=='video-add':raise ValueError('network error')
        player.command.side_effect=command
        with patch.object(quality,'Player',return_value=player),self.assertRaises(ValueError):
            quality.switch('socket','https://example/new','720p')
        self.assertFalse(any(c.args[0] in ('loadfile','set_property','video-remove','audio-remove') for c in player.command.call_args_list))
