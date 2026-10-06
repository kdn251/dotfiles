"""Queue row moves preserve identities, playback order, selection and undo."""
import json
import os
import unittest
from unittest.mock import patch
import newsboat_queue as queue
from test_newsboat_queue import isolated,URLS
from test_newsboat_reconnect import reader

class QueueMoveTests(unittest.TestCase):
    def test_reorder_and_undo_preserve_membership_and_playback_order(self):
        with isolated():
            for url in URLS:queue.change('add',url)
            original=queue.entries()
            queue.navigation(URLS[0])
            queue.change('started',URLS[0],original[0]['queue_token'])
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='move-one'):
                queue.change('move-after',URLS[1],URLS[3])
            self.assertEqual(queue.entries(),[original[i] for i in (0,2,3,1)])
            self.assertEqual(queue.navigation(URLS[0])[0],original[2])
            self.assertEqual(queue.navigation(URLS[1])[1],original[3])
            self.assertEqual(queue.read_state('queue-current.json'),original[0])
            with patch.dict(os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='move-two'):
                queue.change('move-before',URLS[3],URLS[0])
            self.assertEqual(queue.entries(),[original[i] for i in (3,0,2,1)])
            queue.change('restore',URLS[3],'move-two')
            queue.change('restore',URLS[1],'move-one')
            self.assertEqual(queue.entries(),original)
            self.assertEqual(queue.navigation(URLS[0])[0],original[1])
            queue.change('move-after',URLS[0],URLS[0])
            self.assertEqual(queue.entries(),original)
            queue.change('remove',URLS[1])
            with self.assertRaises(ValueError):queue.change('move-after',URLS[1],URLS[2])
            self.assertEqual(len(queue.entries()),3,'a removed copied video is never recreated')

    def test_real_yy_p_P_and_undo_keep_cursor_on_moved_row(self):
        with isolated() as (root,_):
            for url in URLS:queue.change('add',url)
            original=queue.entries()
            queue.media.atomic_write(queue.state()/'queue-durations.json',json.dumps({queue.identity(url):dict(duration=600) for url in URLS}))
            view=root/'view';view.mkdir();_,config=queue.prepare_view(view)
            generated=config.read_text()
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticlelist-format "%4i %t"\narticle-sort-order date-asc\nrun-on-startup open\nbind U everywhere undo-action\nbind-key j down\nbind-key k up\n'
            cfg+='\n'.join(line for line in generated.splitlines() if line.startswith(('bind yy ','bind p ','bind P ')))+'\n'
            (view/'scripts').symlink_to(queue.SCRIPTS,target_is_directory=True)
            env=dict(XDG_STATE_HOME=str(root),NEWSBOAT_QUEUE_STATUS=str(queue.state()/'viewing-queue.tsv'),NEWSBOAT_QUEUE_VIEW='1',NEWSBOAT_UNDO_FILE=str(root/'undo'),NEWSBOAT_CACHE=str(view/'cache'),NEWSBOAT_URLS_FILE=str(root/'urls'))
            with reader(view,cfg,(view/'history.xml').as_uri()+'\n',env) as (_,screen,send,wait):
                def order():return [int(row.split('Video')[1][0]) for row in screen.display[1:-3] if 'Video' in row]
                wait(lambda _:order()==[0,1,2,3])
                send('p');wait(lambda s:'yy first' in s)
                self.assertFalse((root/'undo').exists())
                send('yy');wait(lambda s:'Queue row picked up' in s)
                self.assertEqual(queue.entries(),original)
                send('jjp');wait(lambda _:order()==[1,2,0,3] and screen.cursor.y==3)
                self.assertEqual(queue.entries(),[original[i] for i in (1,2,0,3)])
                send('kP');wait(lambda _:order()==[1,0,2,3] and screen.cursor.y==2)
                send('U');wait(lambda _:order()==[1,2,0,3] and screen.cursor.y==3)
                send('U');wait(lambda _:order()==[0,1,2,3] and screen.cursor.y==1)
                self.assertEqual(queue.entries(),original)
                self.assertEqual([row.strip().split()[0] for row in screen.display[1:5]],['1','2','3','4'])
                send('p');wait(lambda s:'already here' in s)
                self.assertFalse((root/'undo').exists())
