"""Refresh ship stays level and wraps without invisible padding delays."""
import io
import unittest
from PIL import Image, ImageChops
from newsboat_loading import ship_art
from newsboat_thumbnails import loading_png

class BoatMotionTests(unittest.TestCase):
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
