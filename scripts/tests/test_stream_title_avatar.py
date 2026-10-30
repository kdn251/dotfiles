import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image

spec = importlib.util.spec_from_file_location('avatar', Path(__file__).resolve().parents[1]/'scripts/stream-title-avatar.py')
avatar = importlib.util.module_from_spec(spec)
spec.loader.exec_module(avatar)

class AvatarTests(unittest.TestCase):
    def test_cached_portraits_have_rounded_transparent_corners(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(avatar.Path, 'home', return_value=Path(tmp)):
            source = Path(tmp)/'.cache/twitch-profiles/example.png'
            source.parent.mkdir(parents=True)
            Image.new('RGB', (70, 70), (255, 0, 0)).save(source)
            other = {'icon': str(source)}
            with patch.object(avatar, 'load', return_value={s: {'example': other} for s in ('k','r','y')}):
                for service in ('Twitch', 'Kick', 'YouTube', 'Rumble'):
                    result = Path(avatar.prepare(service, 'Example'))
                    data = result.read_bytes()
                    self.assertEqual(len(data), 96*96*4)
                    self.assertEqual(data[:4], bytes(4))
                    center = (48*96+48)*4
                    self.assertEqual(data[center:center+4], bytes((0,0,255,255)))
                    self.assertEqual(avatar.prepare(service, 'Example'), str(result))
            self.assertEqual(avatar.prepare('Twitch', '../invalid'), '')

    def test_unsaved_twitch_channel_fetches_missing_avatar(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(avatar.Path, 'home', return_value=Path(tmp)):
            image = Path(tmp)/'fetched.png'
            Image.new('RGB', (70,70), 'blue').save(image)
            reply = {'data': {'user': {'profileImageURL': 'https://example.test/avatar.png'}}}
            with patch.object(avatar, 'cache_avatar', side_effect=['', str(image)]) as cache, \
                    patch.object(avatar, 'urlopen', return_value=io.BytesIO(json.dumps(reply).encode())):
                self.assertTrue(Path(avatar.prepare('Twitch', 'NotSaved')).is_file())
                cache.assert_called_with('https://www.twitch.tv/notsaved', 'https://example.test/avatar.png')

    def test_unsaved_other_platform_uses_matching_selected_channel(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(avatar.Path, 'home', return_value=Path(tmp)), \
                patch.object(avatar, 'load', return_value={}):
            image = Path(tmp)/'avatar.png'
            Image.new('RGB', (70,70), 'blue').save(image)
            cache = Path(tmp)/'.cache'
            cache.mkdir()
            for service in ('Kick', 'YouTube', 'Rumble'):
                (cache/f'{service.lower()}-live-player.json').write_text(json.dumps({'name':'NotSaved','icon':str(image)}))
                self.assertTrue(Path(avatar.prepare(service, 'NotSaved')).is_file())
                self.assertEqual(avatar.prepare(service, 'Different'), '')
