"""Rapid read shortcuts must never turn previously read rows unread."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from test_newsboat_reconnect import reader, pyte, BINARY

CONFIG=Path(__file__).resolve().parents[2]/'newsboat/.newsboat/config'

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class ReadKeyTests(unittest.TestCase):
    def test_rapid_marks_are_idempotent_in_visible_and_unread_lists(self):
        bindings='\n'.join(line for line in CONFIG.read_text().splitlines()
                           if line.startswith(('bind n ', 'bind N ')))
        for show_read in ('yes','no'):
            with self.subTest(show_read=show_read), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);rss=root/'feed.xml'
                rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>Item {i:02}</title><guid>{i:02}</guid><link>https://example.com/{i}</link></item>' for i in range(12))+'</channel></rss>')
                config=f'show-read-feeds yes\nshow-read-articles {show_read}\nconfirm-exit no\narticle-sort-order guid-asc\n'+bindings+'\nbind g articlelist home\n'
                with reader(root,config,rss.as_uri()+'\n') as (_,screen,send,wait):
                    send('\n');wait(lambda s:'Item 00' in s)
                    send('n'*6)
                    wait(lambda s:'Item 06' in screen.display[screen.cursor.y])
                    if show_read=='yes':
                        send('g');wait(lambda s:'Item 00' in screen.display[screen.cursor.y])
                    send('n'*20+'q')
                    wait(lambda s:'Your feeds' in s)
                    with sqlite3.connect(root/'cache') as db:
                        self.assertEqual(db.execute('SELECT COUNT(*) FROM rss_item WHERE unread=1').fetchone()[0],0)

class ReadQueueTests(unittest.TestCase):
    def test_rapid_read_queue_retries_and_preserves_undo_order(self):
        import importlib.util,json
        from unittest.mock import patch
        helper=CONFIG.parents[2]/'scripts/scripts/newsboat-starred.py'
        spec=importlib.util.spec_from_file_location('read_queue',helper)
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'star-actions';queue.mkdir()
            cache=root/'cache'
            with sqlite3.connect(cache) as db:
                db.execute('CREATE TABLE rss_item (guid TEXT, url TEXT, unread INTEGER)')
                db.executemany('INSERT INTO rss_item VALUES (?,?,1)',[(str(i),f'https://example.com/{i}') for i in range(1,13)])
            actions=[dict(url=f'https://example.com/{i}',desired=None,restore_unread=False,cache=str(cache)) for i in range(1,13)]
            actions.append(dict(actions[0],restore_unread=True))
            for i,action in enumerate(actions):
                (queue/f'{i:03}.json').write_text(json.dumps(action))
            class Server:
                attempts=0
                changes=[]
                def starred(self):raise AssertionError('Read-only actions must not fetch Starred')
                def request(self,path,data=None,method=None):
                    if path.startswith('entries/'):
                        ident=int(path.split('/')[-1]);return dict(id=ident,url=f'https://example.com/{ident}')
                    self.attempts+=1
                    if self.attempts==3:raise OSError('Temporary connection failure')
                    self.changes.append((data['entry_ids'][0],data['status']))
            server=Server()
            with patch.object(worker,'STARRED_STATUS',root/'stars'),patch.object(worker,'Client',return_value=server),patch.object(worker.time,'sleep'):
                worker.drain_star_actions()
            self.assertEqual(server.changes,[(i,'read') for i in range(1,13)]+[(1,'unread')])
            self.assertFalse(list(queue.glob('*.json')))
            with sqlite3.connect(cache) as db:
                self.assertEqual(db.execute('SELECT guid FROM rss_item WHERE unread=1').fetchall(),[('1',)])

    def test_failed_update_remains_queued_for_recovery(self):
        import importlib.util,json
        from unittest.mock import patch
        helper=CONFIG.parents[2]/'scripts/scripts/newsboat-starred.py'
        spec=importlib.util.spec_from_file_location('read_queue_failure',helper)
        worker=importlib.util.module_from_spec(spec);spec.loader.exec_module(worker)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);queue=root/'star-actions';queue.mkdir()
            job=queue/'001.json';job.write_text(json.dumps(dict(url='https://example.com/1')))
            with patch.object(worker,'STARRED_STATUS',root/'stars'),patch.object(worker,'apply_queued_action',side_effect=OSError('offline')) as apply,patch.object(worker.time,'sleep'),patch.object(worker.subprocess,'run'):
                worker.drain_star_actions()
                self.assertEqual(apply.call_count,3)
                self.assertTrue(job.exists())
            with patch.object(worker,'STARRED_STATUS',root/'stars'),patch.object(worker,'apply_queued_action') as apply:
                worker.drain_star_actions()
                apply.assert_called_once()
                self.assertFalse(job.exists())

@unittest.skipUnless(pyte and BINARY.exists(), 'requires native Newsboat and pyte')
class NewReadContentionTests(unittest.TestCase):
    def test_rapid_new_marks_survive_background_database_writer(self):
        import json,threading,time
        bindings='\n'.join(line for line in CONFIG.read_text().splitlines()
                           if line.startswith(('bind n ', 'bind N ')))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rss=root/'feed.xml'
            rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>Item {i:03}</title><guid>{i:03}</guid><link>https://example.com/{i}</link></item>' for i in range(80))+'</channel></rss>')
            config='show-read-feeds yes\nshow-read-articles no\nconfirm-exit no\nscrolloff 999\narticle-sort-order guid-asc\n'+bindings+'\n'
            urls=json.dumps('query:📬 New:unread = "yes"',ensure_ascii=False)+'\n'+rss.as_uri()+'\n'
            with reader(root,config,urls) as (_,screen,send,wait):
                send('\n');wait(lambda s:'Item 000' in s)
                locked=threading.Event()
                def background_writer():
                    db=sqlite3.connect(root/'cache')
                    try:
                        db.execute('BEGIN IMMEDIATE')
                        locked.set()
                        time.sleep(.3)
                        db.commit()
                    finally:db.close()
                writer=threading.Thread(target=background_writer);writer.start()
                self.assertTrue(locked.wait(2))
                send('n'*60)
                wait(lambda s:'Item 060' in screen.display[screen.cursor.y],10)
                writer.join()
                with sqlite3.connect(root/'cache') as db:
                    actual=[row[0] for row in db.execute('SELECT guid FROM rss_item WHERE unread=0 ORDER BY guid')]
                self.assertEqual(actual,[f'{i:03}' for i in range(60)])
                send('q\n');wait(lambda s:'Item 060' in s)
                self.assertNotIn('Item 000','\n'.join(screen.display))
                # A lock longer than the retry budget must leave the failed
                # item selected instead of silently consuming it and advancing.
                locked.clear()
                def long_writer():
                    db=sqlite3.connect(root/'cache')
                    try:
                        db.execute('BEGIN IMMEDIATE');locked.set()
                        time.sleep(5.5);db.commit()
                    finally:db.close()
                writer=threading.Thread(target=long_writer);writer.start()
                self.assertTrue(locked.wait(2))
                send('n')
                wait(lambda s:'Error while toggling read flag' in s,8)
                self.assertIn('Item 060',screen.display[screen.cursor.y])
                writer.join()
                send('n');wait(lambda s:'Item 061' in screen.display[screen.cursor.y])
                with sqlite3.connect(root/'cache') as db:
                    self.assertEqual(db.execute('SELECT unread FROM rss_item WHERE guid="060"').fetchone()[0],0)
