"""Refresh ship stays level and wraps without invisible padding delays."""
import io
import unittest
from PIL import Image, ImageChops
from newsboat_loading import ship_art
from newsboat_thumbnails import loading_png

class BoatMotionTests(unittest.TestCase):
    def test_thumbnail_uses_the_same_traveling_ship(self):
        for frame in (0,8,96,106,150,239):
            self.assertEqual(loading_png(frame),loading_png(frame,traveling=True))

    def test_text_ship_stays_level(self):
        for frame in range(250):
            rows=ship_art(frame,34,traveling=True)
            self.assertEqual(len(rows),6)
            for index,(_,row) in enumerate(rows):
                if '_o_o_' in row:self.assertEqual(index,4)
            self.assertIn('~',rows[5][1])

    def test_image_ship_wraps_on_next_frame_at_fixed_height(self):
        blank=[];bottoms=set();previous=None;wrapped=False
        for frame in range(240):
            image=Image.open(io.BytesIO(loading_png(frame,traveling=True)))
            region=image.crop((8,40,672,232)).convert('RGB')
            bounds=ImageChops.difference(region,Image.new('RGB',region.size,'#1e1e2e')).getbbox()
            if not bounds:
                blank.append(frame)
            else:
                if bounds[0]>5 and bounds[2]<659:bottoms.add(bounds[3])
                if previous and previous[0]>600 and bounds[0]<10:wrapped=True
                previous=bounds
        self.assertEqual(len(bottoms),1)
        self.assertTrue(wrapped)
        self.assertFalse(any(b==a+1 for a,b in zip(blank,blank[1:])),blank)

    def test_startup_ship_moves_level_and_wraps_without_a_gap(self):
        import re
        import subprocess
        from pathlib import Path
        script=Path(__file__).resolve().parents[1]/'scripts/newsboat-launch.sh'
        command=''.join(f'{frame}\tsetting sail\t80\t24\n' for frame in range(0,404,4))
        result=subprocess.run(['bash',str(script),'--render'],input=command,text=True,capture_output=True,check=True)
        frames=[re.sub(r'\x1b\[[0-9;?]*[A-Za-z]','',frame).splitlines() for frame in result.stdout.split('\0')[:-1]]
        deck=next(i for i,row in enumerate(frames[0]) if '___|___________________|___' in row)
        water=next(i for i,row in enumerate(frames[0]) if '~' in row)
        positions=[]
        for rows in frames:
            self.assertTrue(rows[deck].strip(),'the ship returns on the very next step')
            positions.append(len(rows[deck])-len(rows[deck].lstrip()))
            self.assertLessEqual(len(rows[deck].rstrip()),72)
            self.assertGreaterEqual(positions[-1],8)
            self.assertIn('~',rows[water])
            for index,row in enumerate(rows):
                if '\\______________________/' in row:self.assertEqual(index,deck+2)
        wrap=next(i for i in range(1,len(positions)) if positions[i]<positions[i-1])
        self.assertEqual(positions[wrap-1:wrap+1],[71,8])
        self.assertEqual(positions[:5],[26,27,28,29,30])
