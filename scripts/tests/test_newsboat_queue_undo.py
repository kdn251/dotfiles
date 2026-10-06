import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import newsboat_queue as queue
from test_newsboat_queue import isolated,URLS
from test_newsboat_reconnect import reader

class QueueUndoTests(unittest.TestCase):
    def test_multiple_changes_restore_order_tokens_and_navigation(self):
        with isolated():
            for url in URLS[:3]:queue.change('add',url)
            original=queue.entries()
            queue.navigation(URLS[1])
            queue.change('started',URLS[1],original[1]['queue_token'])
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='first'):
                queue.change('remove',URLS[1])
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='second'):
                queue.change('add',URLS[3])
            queue.change('restore',URLS[3],'second')
            queue.change('restore',URLS[1],'first')
            self.assertEqual(queue.entries(),original)
            self.assertEqual(queue.navigation(URLS[1]),(original[2],original[0],original[2]))
            self.assertEqual(queue.read_state('queue-current.json'),original[1])
            # Adding an already queued item and undoing it must retain that item.
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='noop'):
                queue.change('add',URLS[1])
            queue.change('restore',URLS[1],'noop')
            self.assertEqual(queue.entries(),original)

    def test_native_queue_actions_and_bulk_undo(self):
        with isolated() as (root,_):
            (root/'scripts').symlink_to(queue.SCRIPTS,target_is_directory=True)
            for url in URLS[:3]:queue.change('add',url)
            original=queue.entries()
            view=root/'view';view.mkdir();queue.prepare_view(view)
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order title-asc\narticlelist-format "%4i %t"\nrun-on-startup open\nbind U everywhere undo-action\nbind V articlelist visual-rows\nbind-key j down\n'
            main=(queue.SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text()
            cfg+='\n'.join(line for line in main.splitlines() if line.startswith(('macro w ','macro W ')))+'\n'
            # Native helper resolves ~/scripts relative to the reader's HOME.
            (view/'scripts').symlink_to(queue.SCRIPTS,target_is_directory=True)
            env=dict(XDG_STATE_HOME=str(root),NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_QUEUE_VIEW='1',NEWSBOAT_UNDO_FILE=str(root/'undo'),NEWSBOAT_CACHE=str(view/'cache'),NEWSBOAT_URLS_FILE=str(root/'urls'))
            with reader(view,cfg,(view/'history.xml').as_uri()+'\n',env) as (_,screen,send,wait):
                def rows():return [r for r in screen.display[1:-3] if 'Video' in r]
                wait(lambda _:len(rows())==3)
                send(',W');wait(lambda _:len(rows())==2 and len(queue.entries())==2)
                send('U');wait(lambda s:len(rows())==3 and 'Queue change undone' in s)
                self.assertEqual(queue.entries(),original)
                send('Vj,W');wait(lambda _:len(queue.entries())==1)
                send('U');wait(lambda s:len(queue.entries())==3 and 'Queue change undone: 2 items' in s)
                self.assertEqual(queue.entries(),original)
                send(',W');wait(lambda _:len(queue.entries())==2)
                send(',w');wait(lambda _:len(queue.entries())==2) # existing row stays queued
                send('U');wait(lambda _:len((root/'undo').read_text().splitlines())==1)
                self.assertEqual(len(queue.entries()),2)
                send('U');wait(lambda _:len(queue.entries())==3)

    def test_w_opens_queue_from_home_list_and_article(self):
        with isolated() as (root,_):
            scripts=root/'scripts';scripts.mkdir()
            log=root/'opened'
            (scripts/'newsboat_queue.py').write_text('from pathlib import Path\np=Path('+repr(str(log))+')\np.write_text(p.read_text()+"open\\n" if p.exists() else "open\\n")\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description><item><title>Video</title><link>https://example.com/video</link><guid>video</guid><description>Article text</description></item></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nbind w everywhere set browser "newsboat-queue://show"\n'
            with reader(root,cfg,feed.as_uri()+'\n') as (_,screen,send,wait):
                wait(lambda s:'Source' in s)
                for index in range(3):
                    send('w');wait(lambda _:log.exists() and len(log.read_text().splitlines())==index+1)
                    if index<2:send('\n');wait(lambda s:'Video' in s)
