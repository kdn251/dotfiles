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

    def test_trailing_batch_separator_is_not_part_of_window_selector(self):
        code = compat.translate_batch('dispatch pin address:0x123; dispatch pin address:0x456; ')
        self.assertIn('["window"]="address:0x456"', code)
        self.assertNotIn('0x456;', code)
        self.assertEqual(code.count('hl.dispatch('), 2)

    def test_exec_shell_semicolon_is_preserved(self):
        code = compat.translate_batch('dispatch exec echo one; echo two; dispatch pin address:0x123;')
        self.assertIn('echo one; echo two', code)
        self.assertIn('["window"]="address:0x123"', code)

    def test_legacy_gap_field_preserves_current_values(self):
        data = compat.legacy_json({'option':'general:gaps_out', 'css':'6 9 9 9', 'set':True})
        self.assertEqual(data['custom'], '6 9 9 9')
        self.assertEqual(data['css'], '6 9 9 9')

    def test_legacy_boolean_field_does_not_default_to_zero(self):
        data = compat.legacy_json({'option':'input:special_fallthrough', 'bool':True})
        self.assertEqual(data['int'], 1)
        self.assertIs(data['bool'], True)

    def test_special_workspace_ids_are_consistent_across_queries(self):
        workspace = {'address':'special:scratch','name':'special:scratch','type':'special'}
        a = compat.legacy_json([dict(workspace)])[0]
        b = compat.legacy_json({'workspace':dict(workspace)})['workspace']
        self.assertEqual(a['id'], b['id'])
        self.assertLess(a['id'], 0)

if __name__ == '__main__':
    unittest.main()
