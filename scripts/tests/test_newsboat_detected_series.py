import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch,Mock
import newsboat_detected_series as series
import newsboat_youtube_playlists as library
import newsboat_playthroughs as playthroughs
import newsboat_media as media

CHANNEL='UC7_YxT-KID8kRbqZo7MyscQ'

class DetectedSeriesTests(unittest.TestCase):
    def test_conservative_episode_names(self):
        self.assertEqual(series.episode('THE DEEP & THE SHEEP | REANIMAL - Part 4'),
                         ('REANIMAL','reanimal',4))
        self.assertEqual(series.episode('REANIMAL — Episode 10')[2],10)
        self.assertIsNone(series.episode('My top 4 games'))
        self.assertIsNone(series.episode('Part 4'))

    def test_search_save_single_episode_refresh_and_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            entries=[dict(id=f'abcdefghij{i}',title=f'Title | REANIMAL - Part {i}',channel_id=CHANNEL)
                     for i in (4,2,1,3)]
            entries += [dict(id='xxxxxxxxxxx',title='REANIMAL - Part 5',channel_id='other'),
                        dict(id='yyyyyyyyyyy',title='Another game - Part 1',channel_id=CHANNEL)]
            result=Mock(returncode=0,stdout=json.dumps({'entries':entries}))
            with patch.object(library,'LIBRARY',root/'library'),                     patch.object(series,'title_for',return_value='Title | REANIMAL - Part 4'),                     patch.object(library.subprocess,'run',return_value=result) as request,                     patch.object(media,'STATE',root/'state/downloads'):
                row=series.detect(library,'https://www.youtube.com/watch?v=abcdefghij4',
                    'https://www.youtube.com/channel/'+CHANNEL,{'channel_id':CHANNEL,'channel':'Markiplier'})
                self.assertIn('/search?query=REANIMAL',request.call_args.args[0][-1])
                name,videos=library.videos(row['url'])
                self.assertEqual([r['url'][-1] for r in videos],['1','2','3','4'])
                context=root/'context'
                context.write_text(json.dumps(dict(url=row['url'],name=name,channel='Markiplier',rows=videos)))
                playthroughs.record(videos[0]['url'],context)
                group=next(playthroughs.read_groups())
                self.assertEqual(group['selected_urls'],[videos[0]['url']])
                self.assertEqual(len(group['rows']),4)
                self.assertEqual(library.channel_for('newsboat-playthroughs://'+group['id']),
                                 'https://www.youtube.com/channel/'+CHANNEL)
                result.stdout=json.dumps({'entries':[dict(id='abcdefghij5',title='REANIMAL - Part 5',channel_id=CHANNEL)]})
                name,videos=library.videos(row['url'],True)
                self.assertEqual(len(videos),5)
                playthroughs.record_rows(dict(url=row['url'],name=name,channel='Markiplier',rows=videos),selected=[])
                self.assertEqual(next(playthroughs.read_groups())['selected_urls'],[videos[0]['url']])
                request.side_effect=OSError('offline')
                self.assertEqual(len(library.videos(row['url'],True)[1]),5)
