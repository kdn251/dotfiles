import json
from pathlib import Path
import tempfile
import unittest
from test_newsboat_reconnect import reader

class HomeColumnsTests(unittest.TestCase):
    def test_queue_estimates_keep_home_titles_aligned(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description></channel></rss>')
            queue=root/'queue';queue.write_text('')
            summary=root/'queue.time';summary.write_text('~5h 20 mins\n')
            urls=''.join(json.dumps('query:'+title+':unread = "yes"',ensure_ascii=False)+'\n' for title in ['📺 Queue','📬 New','⭐ Starred'])+feed.as_uri()+'\n'
            config='show-read-feeds yes\nprepopulate-query-feeds yes\nfeedlist-format " %3i  %n %S  %4v %-6k  %t"\n'
            with reader(root,config,urls,dict(NEWSBOAT_QUEUE_STATUS=str(queue))) as (_,screen,send,wait):
                for label in ['~5h 20 mins','~34 mins','~125h 20 mins']:
                    summary.write_text(label+'\n')
                    wait(lambda s:label in s and 'Starred' in s)
                    positions=[]
                    for name in ['Queue','New','Starred']:
                        row=next(i for i,line in enumerate(screen.display) if i > 0 and name in line)
                        positions.append(next(x for x in range(screen.columns) if ''.join(screen.buffer[row][x+j].data for j in range(len(name)))==name))
                    self.assertEqual(len(set(positions)),1,(positions,screen.display))
