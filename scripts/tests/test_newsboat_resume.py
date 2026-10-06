"""Collection resume selection and native Queue-row playback shortcut."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_resume as resume
import newsboat_queue as queue
import newsboat_media as media
from test_newsboat_reconnect import reader

ROWS=[dict(url='https://www.youtube.com/watch?v='+str(i)*11,title='Part '+str(i)) for i in range(4)]

class ResumeTests(unittest.TestCase):
    def test_first_unstarted_then_recent_position_then_next_unfinished(self):
        with patch.object(resume,'progress',return_value={}) as progress:
            self.assertEqual(resume.playlist_row(ROWS),ROWS[0])
            progress.return_value={resume.key(ROWS[0]):(.4,30),resume.key(ROWS[1]):(.7,20)}
            self.assertEqual(resume.playlist_row(ROWS),ROWS[0],'recency, not highest percentage')
            progress.return_value={resume.key(ROWS[0]):(1,30),resume.key(ROWS[1]):(1,20)}
            self.assertEqual(resume.playlist_row(ROWS),ROWS[2])
            progress.return_value={resume.key(row):(1,i) for i,row in enumerate(ROWS)}
            self.assertEqual(resume.playlist_row(ROWS),ROWS[0])
            self.assertIsNone(resume.playlist_row([]))

    def test_queue_keeps_current_for_resume_then_advances_after_completion(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_URLS_FILE=folder+'/absent'),patch.object(media,'STATE',Path(folder)/'downloads'),patch.object(queue,'metadata',side_effect=lambda url:dict(url=url,title=url,source='Creator')),patch.object(resume,'launch',return_value=0) as launch,patch.object(resume,'progress',return_value={}) as progress:
            queue.change('add',ROWS[0]['url']);queue.change('add',ROWS[1]['url'])
            queue.resume();self.assertEqual(launch.call_args.args[0]['url'],ROWS[0]['url'])
            token=queue.entries()[0]['queue_token'];queue.change('started',ROWS[0]['url'],token)
            self.assertEqual(len(queue.entries()),1)
            queue.resume();self.assertEqual(launch.call_args.args[0]['url'],ROWS[0]['url'])
            progress.return_value={resume.key(ROWS[0]):(1,100)}
            queue.resume();self.assertEqual(launch.call_args.args[0]['url'],ROWS[1]['url'])

    def test_native_home_o_dispatches_queue_resume_without_opening_list(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);scripts=root/'scripts';scripts.mkdir();called=root/'called'
            (scripts/'newsboat_queue.py').write_text('from pathlib import Path\nimport sys\nPath('+repr(str(called))+').write_text(sys.argv[1])\n')
            text='show-read-feeds yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format "%t"\nbind o feedlist open-in-browser-noninteractively\n'
            with reader(root,text,'"query:📺 Queue:link = \\"placeholder\\""\n') as (_,screen,send,wait):
                wait(lambda s:'Queue' in s)
                send('o');wait(lambda _:called.exists())
                self.assertEqual(called.read_text(),'resume')
                self.assertIn('feeds',screen.display[0].lower())

    def test_playthrough_launch_retains_episode_context(self):
        import newsboat_playthroughs as library
        group=dict(id='PLtest',rows=ROWS)
        with patch.object(library,'read_groups',return_value=iter([group])),patch.object(library,'directory',return_value=Path('/tmp/contexts')),patch.object(resume,'playlist_row',return_value=ROWS[2]),patch.object(resume,'launch',return_value=0) as launch:
            self.assertEqual(resume.playthrough('newsboat-playthroughs://PLtest'),0)
            launch.assert_called_once_with(ROWS[2],Path('/tmp/contexts/PLtest.json'))
