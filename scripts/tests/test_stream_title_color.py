import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('stream_title_color',Path(__file__).resolve().parents[1]/'scripts/stream-title-color.py')
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)

class TitleEmojiTests(unittest.TestCase):
    def test_orphan_selectors_do_not_form_emoji_runs(self):
        self.assertEqual(renderer.runs('text ️ more'),[(False,'text  more')])
        self.assertEqual(renderer.runs('️text'),[(False,'text')])

    def test_valid_emoji_sequences_stay_together(self):
        for text in ('🔴️','👩\u200d💻','🇺🇸','1️⃣','#️⃣','👍🏽'):
            self.assertEqual(renderer.runs(text),[(True,text)])

    @unittest.skipUnless(renderer.APPLE.is_file(),'Apple emoji font required')
    def test_actual_problem_title_renders_color_pixels(self):
        title='🔴 PRO SCRIMS WITH PETERBOT POLLO AND RISE 🔴️ FNCS READY 🔴️ GTA 6 MARATHON S00N 🔴 JOIN UP 🔴 ️ !CLIPPING !COM'
        result=renderer.render(title,'sans-serif')
        raw=Path(result['path']).read_bytes()
        self.assertEqual(len(raw),result['width']*result['height']*4)
        self.assertTrue(any(raw[i+2]>raw[i]+30 and raw[i+2]>raw[i+1]+30 and raw[i+3]>100 for i in range(0,len(raw),4)))

if __name__=='__main__':unittest.main()
