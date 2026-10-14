import importlib.util
from pathlib import Path
import unittest
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
