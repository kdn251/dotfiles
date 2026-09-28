"""Pending collection indicators survive cursor movement and clear on completion."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import newsboat_actions as actions
from test_newsboat_reconnect import reader,pyte,BINARY


class ActionTests(unittest.TestCase):
    def test_failure_clears_marker(self):
        with tempfile.TemporaryDirectory() as directory:
            marker=actions.begin('https://example.com/item',directory)
            @actions.busy
            def fail(url):raise ValueError('failed')
            with patch.object(actions,'begin',return_value=marker):
                with self.assertRaises(ValueError):fail('https://example.com/item')
            self.assertFalse(marker.exists())

    def test_collection_queue_preserves_order_and_clears_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);script=str(root/'collection.py');url='https://example.com/item'
            with patch('subprocess.Popen'):
                actions.enqueue_collection(script,root,['save',url])
                actions.enqueue_collection(script,root,['remove',url])
                actions.enqueue_collection(script,root,['restore',url,'saved'])
            self.assertEqual(len(list((root/'actions-pending').glob('*.txt'))),3)
            calls=[]
            def save(url):calls.append('save')
            def remove(url):
                calls.append('remove')
                raise ValueError('write failed')
            def restore(url,saved):calls.append(('restore',saved))
            with patch('subprocess.run') as notify:
                actions.drain_collection(script,root,dict(save=save,remove=remove,restore=restore))
                notify.assert_called_once()
            self.assertEqual(calls,['save','remove',('restore',True)])
            self.assertEqual(list((root/'actions-pending').glob('*.txt')),[])

    @unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
    def test_spinner_stays_on_item_and_clears_without_moving_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);rss=root/'feed.xml';stars=root/'stars'
            rss.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>test</description>'+''.join(f'<item><title>Item {i}</title><guid>{i}</guid><link>https://example.com/{i}</link></item>' for i in range(3))+'</channel></rss>')
            config='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order guid-asc\narticlelist-format "%p %t"\nbind-key j down\n'
            frames=set('⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏')
            with reader(root,config,rss.as_uri()+'\n',{'NEWSBOAT_STARRED_STATUS':str(stars),'NEWSBOAT_DOWNLOAD_STATUS':str(root/'downloads')}) as (_,screen,send,wait):
                send('\n');wait(lambda s:'Item 0' in s)
                marker=actions.begin('https://example.com/0',root)
                wait(lambda s:bool(set(screen.display[1]) & frames))
                first=screen.display[1]
                wait(lambda s:screen.display[1]!=first)
                send('j');wait(lambda s:'Item 1' in screen.display[screen.cursor.y])
                self.assertTrue(set(screen.display[1]) & frames)
                stars.write_text('https://example.com/0\n');actions.finish(marker)
                wait(lambda s:not(set(s) & frames))
                self.assertIn('Item 1',screen.display[screen.cursor.y])
                self.assertIn('󰓎',screen.display[1])
                (root/'stars.commentary').write_text('https://example.com/0\n')
                (root/'stars.favorites').write_text('https://example.com/0\n')
                for kind,symbol in [('star','󰓎'),('commentary','📣'),('favorites','')]:
                    marker=actions.begin('https://example.com/0',root,remove=kind)
                    wait(lambda s:bool(set(screen.display[1]) & frames) and symbol not in screen.display[1])
                    for other in {'󰓎','📣',''}-{symbol}:
                        self.assertIn(other,screen.display[1])
                    actions.finish(marker)
                    # A failed removal leaves the saved state intact and restores its icon.
                    wait(lambda s:not(set(s) & frames) and symbol in screen.display[1])
                    self.assertIn('Item 1',screen.display[screen.cursor.y])

