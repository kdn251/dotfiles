import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
spec=importlib.util.spec_from_file_location('follow',Path(__file__).parents[1]/'scripts/media-chat-follow.py')
follow=importlib.util.module_from_spec(spec);spec.loader.exec_module(follow)

class PlacementTests(unittest.TestCase):
    monitor=dict(x=0,y=0,width=2880,height=1920,scale=2,reserved=[0,29,0,0])
    def place(self,x,y=42,monitor=None):
        return follow.placement(dict(at=[x,y],size=[547,308]),dict(size=[144,308]),monitor or self.monitor,[12]*4,1)
    def test_right_player_keeps_chat_left(self):self.assertEqual(self.place(880),[734,42])
    def test_left_player_puts_chat_right(self):self.assertEqual(self.place(13),[562,42])
    def test_bottom_clamped(self):self.assertEqual(self.place(880,900),[734,639])
    def test_monitor_origin(self):
        monitor=dict(self.monitor,x=-1440)
        self.assertEqual(self.place(-1427,monitor=monitor),[-878,42])
    def test_changed_gaps(self):
        self.assertEqual(follow.placement(dict(at=[20,10],size=[547,308]),dict(size=[144,308]),self.monitor,[30]*4,2),[571,61])

    def test_resize_matches_player_height_and_repositions_together(self):
        player=dict(at=[880,439],size=[547,508])
        chat=dict(address='0x123',at=[734,639],size=[144,308])
        with patch.object(follow,'hypr') as hypr:
            follow.follow_geometry(player,chat,self.monitor,[12]*4,1)
            hypr.assert_called_once_with('--batch',
                'dispatch resizewindowpixel exact 144 508,address:0x123; '
                'dispatch movewindowpixel exact 734 439,address:0x123')

    def test_matched_chat_does_not_trigger_repeated_resizes(self):
        with patch.object(follow,'hypr') as hypr:
            follow.follow_geometry(dict(at=[880,439],size=[547,508]),
                dict(address='0x123',at=[734,439],size=[144,508]),self.monitor,[12]*4,1)
            hypr.assert_not_called()

    def test_stream_chat_restores_configured_width(self):
        for title,expected in [('Twitch',144),('Kick live chat',180),('YouTube live chat',360)]:
            with self.subTest(title=title),patch.object(follow,'hypr') as hypr:
                chat=dict(address='0x123',at=[400,439],size=[520,508],title=title,
                          **{'class':'com.chatterino.chatterino' if title=='Twitch' else 'newsboat-live-chat'})
                follow.follow_geometry(dict(at=[880,439],size=[547,508]),chat,self.monitor,[12]*4,1)
                self.assertIn(f'resizewindowpixel exact {expected} 508',hypr.call_args.args[1])

class NativeCommandTests(unittest.TestCase):
    def test_single_chat_commands_are_translated_like_batches(self):
        for args in [('keyword','input:special_fallthrough','0'),
                     ('dispatch','togglespecialworkspace','chatterino_chat'),
                     ('dispatch','focuswindow','address:0x123')]:
            with self.subTest(args=args),patch.object(follow.subprocess,'check_output',return_value='ok') as call:
                follow.hypr(*args)
                self.assertEqual(call.call_args.args[0],
                    ['/usr/bin/hyprctl','eval',follow._compat.translate(' '.join(args))])
