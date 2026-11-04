import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import newsboat_playlist_changes as changes
import newsboat_youtube_playlists as library

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('changes_ui',SCRIPTS/'newsboat-playlists.py')
ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(ui)
spec=importlib.util.spec_from_file_location('changes_local_ui',SCRIPTS/'newsboat-playthroughs.py')
local_ui=importlib.util.module_from_spec(spec);spec.loader.exec_module(local_ui)
URL='https://www.youtube.com/playlist?list=PLtest_changes'
ROWS=[dict(url='https://www.youtube.com/watch?v='+str(i)*11,title=f'Episode {i}',source='Creator',position=i+1) for i in range(3)]

class PlaylistChangesTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        mock=patch.object(library,'LIBRARY',self.root/'library');mock.start();self.addCleanup(mock.stop)

    def test_first_visit_reorder_additions_and_next_visit(self):
        self.assertEqual(changes.additions(ROWS,changes.previous(URL)),[])
        changes.remember(URL,ROWS[:2])
        before=changes.previous(URL)
        self.assertEqual(changes.additions(list(reversed(ROWS[:2])),before),[])
        self.assertEqual(changes.additions(ROWS,before),[ROWS[2]['url']])
        # A fetch on its own doesn't acknowledge the added episode.
        self.assertEqual(changes.additions(ROWS,changes.previous(URL)),[ROWS[2]['url']])
        changes.remember(URL,ROWS)
        self.assertEqual(changes.additions(ROWS,changes.previous(URL)),[])

    def test_migration_and_url_aliases(self):
        old=[dict(ROWS[0],url='https://youtu.be/'+'0'*11)]
        self.assertEqual(changes.additions(ROWS,changes.previous(URL,old)),[r['url'] for r in ROWS[1:]])
        context=library.LIBRARY/'browsed-playlists/PLtest_changes.json'
        context.parent.mkdir(parents=True);context.write_text(json.dumps(dict(rows=ROWS[:2])))
        self.assertEqual(changes.additions(ROWS,changes.previous(URL)),[ROWS[2]['url']])

    def test_remote_and_saved_playlist_row_labels(self):
        data=dict(kind='playlist',name='Series',rows=ROWS,new_urls=[ROWS[2]['url']])
        _,config=ui.prepare_view(self.root,data)
        self.check_rows(config)
        group=dict(id='PLtest_changes',url=URL,name='Series',channel='Creator',rows=ROWS)
        with patch.object(local_ui.library,'groups',return_value=[group]):
            _,config,_=local_ui.prepare_view(self.root,group['id'],changes.keys(ROWS[:2]))
        self.check_rows(config)
        self.assertIn('1 new since last visit',config.read_text())

    def check_rows(self,config):
        items=ET.parse(self.root/'playlist.xml').findall('./channel/item')
        self.assertEqual([i.findtext('title').startswith('NEW · ') for i in items],[False,False,True])
        self.assertEqual([i.findtext('link') for i in items],[r['url'] for r in ROWS])
        self.assertIn('highlight article "NEW ·" default default bold',config.read_text())
        self.assertFalse(any(r['title'].startswith('NEW') for r in ROWS))

    def test_marker_renders_bold_in_newsboat(self):
        from test_newsboat_reconnect import reader, pyte, BINARY
        if not pyte or not BINARY.exists():self.skipTest('requires Newsboat and pyte')
        data=dict(kind='playlist',name='Series',rows=ROWS,new_urls=[ROWS[2]['url']])
        ui.prepare_view(self.root,data)
        config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%i %t"\nhighlight article "NEW ·" default default bold\n'
        with reader(self.root,config,(self.root/'playlist.xml').as_uri()+'\n') as (_,screen,send,wait):
            wait(lambda s:'Series' in s);send('\n')
            wait(lambda s:'NEW · Episode 3 of 3' in s)
            line=next(i for i,text in enumerate(screen.display) if 'NEW ·' in text)
            column=screen.display[line].index('NEW ·')
            self.assertTrue(screen.buffer[line][column].bold)
