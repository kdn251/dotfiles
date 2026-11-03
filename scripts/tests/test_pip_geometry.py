import unittest
from pip_geometry import bounds,bottom_right,align_default

class GeometryTests(unittest.TestCase):
    def test_scaled_laptop_matches_tiled_edges(self):
        mon=dict(width=2880,height=1920,scale=2,x=0,y=0,reserved=[0,37,0,0])
        self.assertEqual(bounds(mon,[6,9,9,9],1),(10,44,1430,950))
        self.assertEqual(bottom_right(mon,[547,308],[6,9,9,9],1),[883,642])
        player=dict(at=[880,639],size=[547,308])
        self.assertEqual(align_default(player,mon,[6,9,9,9],1),[883,642])
        player['at']=[300,200]
        self.assertEqual(align_default(player,mon,[6,9,9,9],1),[300,200])

    def test_external_monitor_offset_scale_and_bottom_panel(self):
        mon=dict(width=3840,height=2160,scale=1.5,x=1440,y=-100,reserved=[0,0,0,40])
        self.assertEqual(bottom_right(mon,[800,450],[12]*4,2),[3186,836])

    def test_rotated_monitor(self):
        mon=dict(width=1920,height=1080,scale=1,transform=1,x=-1080,y=0)
        self.assertEqual(bottom_right(mon,[400,225],[8]*4,1),[-409,1686])

    def test_docked_player_stays_aligned_when_monitor_changes(self):
        import importlib.util,tempfile
        from pathlib import Path
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('restore',Path(__file__).parents[1]/'scripts/restore-pip-position.py')
        restore=importlib.util.module_from_spec(spec);spec.loader.exec_module(restore)
        laptop=dict(id=0,width=2880,height=1920,scale=2,x=0,y=0,reserved=[0,37,0,0])
        external=dict(id=1,width=3840,height=2160,scale=1.5,x=1440,y=0,reserved=[0,37,0,0])
        player=dict(address='test',pid=1,mapped=True,floating=True,fullscreen=0,monitor=0,
                    title='Video',**{'class':'mpv','at':[883,642],'size':[547,308]})
        with tempfile.TemporaryDirectory() as folder,patch.object(restore,'restore') as move:
            tracker=restore.Tracker(folder)
            tracker.update([player],([laptop],[6,9,9,9],1))
            move.assert_not_called()
            player=dict(player,monitor=1,at=[2000,500])
            tracker.update([player],([laptop,external],[6,9,9,9],1))
            move.assert_called_once_with('test',(3443,1122,547,308))
