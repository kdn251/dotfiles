import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from media_panel_layout import FIT, PROPERTY, update
from stream_sidebar import VideoSpace


class SidebarAnimationTests(unittest.TestCase):
    def test_rapid_chat_reopens_never_save_residual_space_or_clear_sidebar(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,XDG_RUNTIME_DIR=folder):
            props=dict(FIT)
            def command(action,key,*args):
                if action=='get_property':return props.get(key)
                props[key]=args[0]
            update(command,123,'left',.1)
            for residual in (.2,.13,.04,.19):
                props['video-margin-ratio-right']=residual
                # Simulate an older saved layout contaminated by a slide.
                props[PROPERTY]['original']['video-margin-ratio-right']=residual
                update(command,123,'right',.2,clear_original_side=True)
                update(command,123,'right',0,clear_original_side=True)
                self.assertEqual(props['video-margin-ratio-right'],0)
                self.assertEqual(props['video-margin-ratio-left'],.1)
            update(command,123,'left',0)
            self.assertEqual(props['video-margin-ratio-right'],0)
            self.assertEqual(props[PROPERTY],{})

    def test_animation_owns_left_margin_without_disturbing_chat_or_saved_layout(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, XDG_RUNTIME_DIR=folder):
            props=dict(FIT)
            def command(action, key, *args):
                if action=='get_property':return props.get(key)
                props[key]=args[0]
            update(command,123,'right',.15)
            Path(folder,'media-sidebar-slide-enabled').touch()
            sidebar=VideoSpace(command,123)
            sidebar.reserve(230,2560)
            self.assertEqual(props['video-margin-ratio-left'],0)
            self.assertAlmostEqual(props[PROPERTY]['left'],230/2560)
            self.assertEqual(props['video-margin-ratio-right'],.15)
            # A compositor frame puts the panel partway across the screen.
            props['video-margin-ratio-left']=.04
            sidebar.restore()
            self.assertEqual(props['video-margin-ratio-left'],.04)
            self.assertEqual(props[PROPERTY]['left'],0)
            self.assertEqual(props['video-margin-ratio-right'],.15)

    def test_without_plugin_margin_still_updates_and_restores(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, XDG_RUNTIME_DIR=folder):
            props=dict(FIT)
            def command(action,key,*args):
                if action=='get_property':return props.get(key)
                props[key]=args[0]
            sidebar=VideoSpace(command,123)
            sidebar.reserve(230,2560)
            self.assertAlmostEqual(props['video-margin-ratio-left'],230/2560)
            sidebar.restore()
            self.assertEqual(props['video-margin-ratio-left'],0)
            self.assertEqual(props[PROPERTY],{})
