"""Regression checks for commands used by desktop shortcuts after 0.57."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('compat', Path(__file__).parents[1] / 'scripts/hyprctl-compat.py')
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

class CompatibilityTests(unittest.TestCase):
    def test_cycle_all_windows_does_not_exclude_tiled_or_floating(self):
        for argument in ('', 'prev'):
            code = compat.dispatcher('cyclenext', argument)
            self.assertNotIn('tiled', code)
            self.assertNotIn('floating', code)
        self.assertIn('["next"]=false', compat.dispatcher('cyclenext', 'prev'))

    def test_explicit_cycle_filter_is_preserved(self):
        code = compat.dispatcher('cyclenext', 'prev tiled')
        self.assertIn('["tiled"]=true', code)
        self.assertNotIn('floating', code)

    def test_preview_geometry_is_absolute_and_targets_preview(self):
        for command in ('movewindowpixel', 'resizewindowpixel'):
            code = compat.dispatcher(command, 'exact 480 270,address:0x123')
            self.assertIn('["relative"]=false', code)
            self.assertIn('["window"]="address:0x123"', code)

    def test_silent_workspace_move_does_not_follow(self):
        code = compat.dispatcher('movetoworkspacesilent', 'special:scratch,address:0x123')
        self.assertIn('["follow"]=false', code)
        self.assertIn('["workspace"]="special:scratch"', code)

if __name__ == '__main__':
    unittest.main()
