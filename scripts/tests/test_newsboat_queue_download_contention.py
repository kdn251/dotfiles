"""Queue commands stay responsive while downloads hold the library lock."""
import threading
import unittest
from unittest.mock import patch
import newsboat_media as media
import newsboat_queue as queue
from test_newsboat_queue import isolated, URLS

class QueueDownloadContentionTests(unittest.TestCase):
    def test_add_remove_and_undo_finish_while_download_library_is_locked(self):
        with isolated() as (root, urls), patch.object(queue.subprocess,'Popen') as spawn:
            errors=[]
            def actions():
                try:
                    with patch.dict(queue.os.environ,NEWSBOAT_QUEUE_UNDO_TOKEN='add'):
                        queue.change('add',URLS[0])
                    queue.change('restore',URLS[0],'add')
                    queue.change('add',URLS[1])
                    queue.change('remove',URLS[1])
                except Exception as error:errors.append(error)
            with media.library_lock():
                thread=threading.Thread(target=actions)
                thread.start();thread.join(2)
                blocked=thread.is_alive()
            thread.join(5)
            self.assertFalse(blocked,'Queue command waited for the download library lock')
            self.assertFalse(errors)
            self.assertEqual(queue.entries(),[])
            self.assertEqual(spawn.call_count,4)
            for call in spawn.call_args_list:
                self.assertEqual(call.args[0][-1],'publish-urls')
                self.assertTrue(call.kwargs['start_new_session'])
            # Delayed publication uses final state and preserves other feeds.
            urls.write_text(urls.read_text()+'https://example.com/downloads.xml\n')
            queue.publish_urls()
            self.assertNotIn('Queue',urls.read_text())
            self.assertIn('https://example.com/downloads.xml',urls.read_text())

    def test_native_navigation_after_rapid_download_and_queue(self):
        import json
        from test_newsboat_reconnect import reader, pyte, BINARY
        if not pyte or not BINARY.exists():self.skipTest('requires native Newsboat and pyte')
        for sequence in (',d,wj,w', ',w,dj,w'):
            with self.subTest(sequence=sequence), isolated() as (root, urls):
                scripts=root/'scripts';scripts.mkdir()
                (scripts/'newsboat_queue.py').symlink_to(queue.SCRIPTS/'newsboat_queue.py')
                # A safe download stand-in; the parent holds the exact library
                # lock a real download rebuild takes. No media/network changes.
                stub=scripts/'newsboat-download-video.sh'
                stub.write_text('#!/bin/sh\nexit 0\n');stub.chmod(0o755)
                feed=root/'feed.xml'
                feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description>'+''.join(
                    f'<item><title>Video{i}</title><link>{url}</link><guid>item{i}</guid><description>Test</description></item>' for i,url in enumerate(URLS))+'</channel></rss>')
                main=(queue.SCRIPTS.parents[1]/'newsboat/.newsboat/config').read_text()
                cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticle-sort-order title-asc\nrun-on-startup open\nbind-key j down\n'
                cfg+='\n'.join(line for line in main.splitlines() if line.startswith(('macro w ','macro d ')))+'\n'
                env=dict(XDG_STATE_HOME=str(root),NEWSBOAT_URLS_FILE=str(urls),NEWSBOAT_CACHE=str(root/'cache'),NEWSBOAT_UNDO_FILE=str(root/'undo'))
                with reader(root,cfg,feed.as_uri()+'\n',env) as (_,screen,send,wait):
                    wait(lambda s:'Video3' in s)
                    with media.library_lock():
                        send(sequence)
                        # The second queued item proves j and the second macro
                        # were processed before the download lock was released.
                        wait(lambda _:len(queue.entries())==2,timeout=2)
                        self.assertEqual(len({row['url'] for row in queue.entries()}),2)
                    wait(lambda _:'Queue' in urls.read_text())
