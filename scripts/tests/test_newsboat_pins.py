"""Pin order, live sorting, cross-view markers, bulk undo and active priority."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_newsboat_reconnect import reader

SCRIPTS=Path(__file__).resolve().parents[1]/'scripts'
spec=importlib.util.spec_from_file_location('pins',SCRIPTS/'newsboat-pins.py')
pins=importlib.util.module_from_spec(spec);spec.loader.exec_module(pins)


class PinTests(unittest.TestCase):
    def test_idempotence_aliases_and_restore_rank(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,XDG_STATE_HOME=folder,NEWSBOAT_PINS_FILE=folder+'/pins.tsv',NEWSBOAT_CACHE=folder+'/missing'):
            a='https://youtu.be/abcdefghijk';b='https://example.org/article'
            pins.change('save',a);pins.change('save',b)
            source,target=pins.paths();before=json.loads(source.read_text())
            pins.change('save','https://www.youtube.com/watch?v=abcdefghijk')
            self.assertEqual(json.loads(source.read_text()),before)
            order=before[pins.key(a)]['order']
            pins.change('remove',a);pins.change('restore',a,order)
            self.assertEqual(json.loads(source.read_text()),before)
            self.assertIn('https://www.youtube.com/watch?v=abcdefghijk\t'+str(order),target.read_text())

    def check_ui(self, bulk=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);feed=root/'feed.xml';helper=SCRIPTS/'newsboat-pins.py'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description>'+''.join(f'<item><title>Item{i}</title><link>https://example.org/{i}</link><guid>{i}</guid></item>' for i in range(1,5))+'</channel></rss>')
            config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order title-asc\narticlelist-format "%4i %p %t"\nrun-on-startup open\nbind-key j down\nbind V articlelist,searchresultslist visual-rows\nbind U everywhere undo-action\n'
            for key,action in [('p','save'),('P','remove')]:
                config+=f'macro {key} undo-checkpoint pin ; set browser "python3 {helper} {action} %u" ; open-in-browser-noninteractively ; set browser "true"\n'
            env=dict(XDG_STATE_HOME=folder,NEWSBOAT_PINS_FILE=str(root/'pins.tsv'),NEWSBOAT_PINS_HELPER=str(helper),NEWSBOAT_UNDO_FILE=str(root/'undo'),NEWSBOAT_DOWNLOAD_STATUS=str(root/'status'),NEWSBOAT_CACHE=str(root/'cache'))
            with reader(root,config,feed.as_uri()+'\n',env) as (_,screen,send,wait):
                def order():return [line.split('Item')[1][0] for line in screen.display[1:-3] if 'Item' in line]
                def selected(n):return 'Item'+str(n) in screen.display[screen.cursor.y]
                wait(lambda _:order()==list('1234'))
                if bulk:
                    send('jVj,p');wait(lambda _:order()==list('2314'))
                    self.assertEqual(sum('📌' in row for row in screen.display[1:-3]),2)
                    send('U');wait(lambda s:order()==list('1234') and 'Pin change undone: 2 items' in s)
                    return
                send(':3\n,p');wait(lambda _:order()==list('3124') and selected(3))
                send(':3\n,p');wait(lambda _:order()==list('3214') and selected(2))
                (root/'status').write_text('https://example.org/4\t↓ 10%\n')
                wait(lambda _:order()==list('4321') and selected(2))
                (root/'status').write_text('https://example.org/4\t↓ 80%\n')
                wait(lambda s:'80%' in s and order()==list('4321'))
                send(',P');wait(lambda _:order()==list('4312') and selected(2))
                send('U');wait(lambda s:order()==list('4321') and 'Pin restored: Item2' in s)
                self.assertEqual(sum('📌' in row for row in screen.display[1:-3]),2)
                send('/Item\n');wait(lambda s:'Search' in screen.display[0] and order()==list('4321'))
                send('q');wait(lambda _:order()==list('4321'))
                (root/'status').write_text('')
                wait(lambda _:order()==list('3214'))
                send(':1\n,P');wait(lambda _:order()==list('2134') and selected(3))
                send(':1\n,P');wait(lambda _:order()==list('1234') and selected(2))
                self.assertFalse(any('📌' in row for row in screen.display[1:-3]))

    def test_live_pin_order_and_cursor(self):self.check_ui()
    def test_bulk_pins_and_undo(self):self.check_ui(bulk=True)
