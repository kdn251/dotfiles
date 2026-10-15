"""Saved multi-platform identities and custom Twitch usernames stay distinct."""
import os
from pathlib import Path
import subprocess
import unittest
SCRIPT=Path(__file__).parents[1]/'scripts/twitch-launcher.sh'

class PickerInputTests(unittest.TestCase):
    def resolve(self,value):
        source=SCRIPT.read_text()
        block=source.split('CHOICE=""\n',1)[1].split('rm -f "$MENU_ORDERED"',1)[0]
        result=subprocess.run(['bash','-c','notify-send() { :; }; CHOICE=""\n'+block+'\nprintf "%s" "$CHOICE"'],env=dict(os.environ,CHOICE_INPUT=value),capture_output=True,text=True,check=True)
        return result.stdout
    def test_custom(self):
        for value in ['Some_Streamer','@Some_Streamer','https://www.twitch.tv/Some_Streamer/']:
            self.assertEqual(self.resolve(value),'some_streamer')
        self.assertEqual(self.resolve('12345'),'12345')
    def test_saved_services(self):
        self.assertEqual(self.resolve('Display name — Gaming · 5k\tDisplay name (YouTube)'),'Display name (YouTube)')
        self.assertEqual(self.resolve('Streamer\tStreamer (Kick)'),'Streamer (Kick)')
        self.assertEqual(self.resolve('twitchname\ttwitchname'),'twitchname')
    def test_cancel_and_invalid(self):
        for value in ['', 'not a username', 'https://example.com/test', '$(touch bad)', 'user;command']:
            self.assertEqual(self.resolve(value),'')
