import unittest
from stream_menu_metadata import details, playback_title, search_rank, highlight
from unittest.mock import patch

class MetadataTests(unittest.TestCase):
    def test_uptime_formats_valid_start_times_only(self):
        from stream_menu_metadata import uptime, format_playback_title
        from datetime import datetime, timezone
        start=datetime(2026,10,30,12,tzinfo=timezone.utc).timestamp()
        for value in (start, '2026-10-30T12:00:00Z', '2026-10-30 12:00:00'):
            self.assertEqual(uptime({'started_at':value},start+8040),'Live 2h 14m')
        self.assertEqual(uptime({'started_at':start},start+59),'Live 0m')
        for value in (None, '', 'bad', True, start+100):
            self.assertEqual(uptime({'started_at':value},start),'')
        with patch('stream_menu_metadata.time.time',return_value=start+8040):
            self.assertIn('Live 2h 14m',format_playback_title('Example',{'started_at':start,'title':'Gaming'}))

    def test_full_labels_preserve_identity(self):
        cache={'t':{'example':{'category':'Grand Theft Auto V','title':'A long\nstream title','viewer_count':12345}}}
        self.assertEqual(details('Example — Grand Theft … · 12.3k','Example — Grand Theft … · 12.3k','t',cache),
                         ('Example','Grand Theft Auto V','A long stream title','12.3k watching'))
    def test_names_rank_above_titles(self):
        rows=[('Other','Chatting','Watching Nadeshot'),('NadeshotClips','',''),('Nadeshot','',''),('xNadeshot','','')]
        ranked=sorted(rows,key=lambda row:search_rank('nadeshot',*row))
        self.assertEqual([r[0] for r in ranked],['Nadeshot','NadeshotClips','xNadeshot','Other'])
        self.assertEqual(search_rank(' @NADESHOT ', 'Nadeshot'),0)
        self.assertEqual(search_rank('ndsh','Nadeshot'),3)
        self.assertIsNone(search_rank('ndsh','Other','New day','Some highlights'))
        self.assertEqual(search_rank('fortnite','Other','Fortnite'),4)
        self.assertEqual(search_rank('', 'Other'),0)

    def test_highlights_are_safe_and_follow_matches(self):
        import xml.etree.ElementTree as ET
        text='A&B <Nadeshot> Nade'
        markup=highlight(text,'nade')
        parsed=ET.fromstring('<root>'+markup+'</root>')
        self.assertEqual(''.join(parsed.itertext()),text)
        self.assertEqual([node.text for node in parsed],['Nade','Nade'])
        parsed=ET.fromstring('<root>'+highlight('Nadeshot','ndsh',True)+'</root>')
        self.assertEqual(''.join(node.text for node in parsed),'Ndsh')
        self.assertEqual(highlight('A&B',''),'A&amp;B')
        parsed=ET.fromstring('<root>'+highlight('Straße','STRASSE')+'</root>')
        self.assertEqual(parsed[0].text,'Straße')

    def test_player_title(self):
        with patch('stream_menu_metadata.load',return_value={'t':{'nadeshot':{'category':'Call of Duty','title':'Ranked with friends','viewer_count':12400}}}):
            self.assertEqual(playback_title('Nadeshot','Twitch'),'Nadeshot — Call of Duty · 12.4k watching | Ranked with friends')
        with patch('stream_menu_metadata.load',return_value={}):
            self.assertEqual(playback_title('Example','YouTube','Live stream title'),'Example | Live stream title')
            self.assertEqual(playback_title('Example','Twitch'),'Example')

    def test_missing_metadata_and_other_service(self):
        self.assertEqual(details('Example — Gaming · 100','Example (Kick)','k',{}),('Example','Gaming','',''))

if __name__=='__main__':unittest.main()
