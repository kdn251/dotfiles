import unittest
from unittest.mock import patch
import newsboat_queue_panel as panel
import newsboat_queue as queue
import newsboat_watch_progress as progress
from test_newsboat_queue import isolated, URLS
from test_newsboat_reconnect import reader

class QueueHeaderTests(unittest.TestCase):
    def test_live_progress_order_and_empty_queue(self):
        with isolated():
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],120,600)
                progress.record(URLS[1],60,1200)
            header=panel.Header();header.update()
            self.assertIn('Video0\tCreator\t━━────── 20% · 8:00 left',header.path.read_text())
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,600)
            header.due=0;header.update()
            self.assertIn('50% · 5:00 left',header.path.read_text())
            queue.change('move-before',URLS[1],URLS[0]);header.due=0;header.update()
            self.assertTrue(header.path.read_text().startswith('Video1\t'))
            for url in URLS[:2]:queue.change('remove',url)
            header.due=0;header.update()
            self.assertEqual(header.path.read_text(),'')

    def test_stop_estimate_tracks_progress_reordering_and_removal(self):
        with isolated():
            for url in URLS[:3]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],120,600)
                progress.record(URLS[1],60,1200)
                progress.record(URLS[2],0,3600)
            queue.change('stop-after',URLS[1])
            header=panel.Header()
            def text():
                header.due=0;header.update()
                return header.path.read_text()
            self.assertIn('💤 Stops in ~27 mins',text())
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,600)
            self.assertIn('💤 Stops in ~24 mins',text())
            queue.change('move-before',URLS[1],URLS[0])
            self.assertIn('💤 Stops in ~19 mins',text())
            queue.change('clear-stop',URLS[1])
            self.assertNotIn('💤',text())
            self.assertIn('19:00 left',text())

    def test_stop_estimate_does_not_guess_unknown_duration(self):
        with isolated():
            queue.change('add',URLS[0]);queue.change('stop-after',URLS[0])
            header=panel.Header();header.update()
            self.assertIn('💤 Stop time unknown',header.path.read_text())

    def test_timed_snooze_marks_video_containing_expiry(self):
        from pathlib import Path
        import time
        with isolated():
            for url in URLS[:3]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],120,600)  # 8 minutes remain
                progress.record(URLS[1],0,1200)  # 20 minutes
                progress.record(URLS[2],0,3600)
            rows=queue.read_state('viewing-queue.json',[])
            self.assertEqual(panel.timed_snooze_target(rows,1900,now=100),URLS[2])
            self.assertEqual(panel.timed_snooze_target(rows,580,now=100),URLS[0])
            self.assertEqual(panel.timed_snooze_target(rows,581,now=100),URLS[1])
            self.assertEqual(panel.timed_snooze_target(rows,10000,now=100),'')
            timer=queue.state()/'viewing-queue.tsv.snooze'
            target=Path(str(timer)+'.target')
            timer.write_text(str(int(time.time())+1800))
            header=panel.Header();header.update()
            self.assertEqual(target.read_text(),URLS[2])
            queue.change('move-before',URLS[2],URLS[0])
            header.due=0;header.update()
            self.assertEqual(target.read_text(),URLS[2])
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[2],3500,3600)
            header.due=0;header.update()
            self.assertEqual(target.read_text(),'')  # Queue now ends before the timer.
            timer.unlink();header.due=0;header.update()
            self.assertEqual(target.read_text(),'')

    def test_timed_target_respects_manual_stop_and_unknown_duration(self):
        rows=[dict(url=URLS[0],stop_after=True),dict(url=URLS[1])]
        with patch.object(panel.queue_time,'remaining_items',return_value=[600,1200]):
            self.assertEqual(panel.timed_snooze_target(rows,900,now=0),'')
            self.assertEqual(panel.timed_snooze_target(rows,300,now=0),URLS[0])
        with patch.object(panel.queue_time,'remaining_items',return_value=[None,1200]):
            self.assertEqual(panel.timed_snooze_target(rows,900,now=0),'')

    def test_native_timed_marker_updates_and_clears(self):
        import os,time
        with isolated() as (root,_):
            for url in URLS[:2]:queue.change('add',url)
            with patch.object(progress,'STATE',queue.state()):
                progress.record(URLS[0],0,600)
                progress.record(URLS[1],0,1200)
            status=queue.state()/'viewing-queue.tsv'
            timer=queue.state()/'viewing-queue.tsv.snooze'
            header=panel.Header()
            timer.write_text(str(int(time.time())+900));header.update()
            view=root/'view';view.mkdir();_,config=queue.prepare_view(view)
            env=dict(NEWSBOAT_QUEUE_VIEW='1',NEWSBOAT_QUEUE_STATUS=str(status))
            with reader(root,config.read_text()+'run-on-startup open\n',(view/'urls').read_text(),env) as (_,screen,send,wait):
                wait(lambda s:'Video1' in screen.display[2] and '💤' in screen.display[2])
                self.assertNotIn('💤',screen.display[1])
                timer.write_text(str(int(time.time())+300));header.due=0;header.update()
                wait(lambda s:'💤' in screen.display[1] and '💤' not in screen.display[2])
                timer.unlink();header.due=0;header.update()
                wait(lambda s:'💤' not in screen.display[1]+screen.display[2])

    def test_native_title_row_on_home_list_and_help(self):
        with isolated() as (root,_):
            queue.change('add',URLS[0])
            with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],120,600)
            header=panel.Header();header.update()
            feed=root/'feed.xml'
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>test</description><item><guid>1</guid><title>Article</title><link>https://example.org/1</link></item></channel></rss>')
            cfg='show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nfeedlist-title-format " Newsboat"\narticlelist-title-format " Source"\n'
            with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_QUEUE_HEADER':str(header.path)}) as (_,screen,send,wait):
                wait(lambda _: 'Newsboat' in screen.display[0] and 'Video0' in screen.display[0])
                self.assertTrue(screen.display[0].endswith('8:00 left '))
                send('\n');wait(lambda _: 'Source' in screen.display[0] and 'Video0' in screen.display[0])
                send('?');wait(lambda _: 'Help' in screen.display[0] and '20%' in screen.display[0])
                with patch.object(progress,'STATE',queue.state()):progress.record(URLS[0],300,600)
                header.due=0;header.update()
                wait(lambda _: '50%' in screen.display[0])
                queue.change('stop-after',URLS[0]);header.due=0;header.update()
                wait(lambda _: '💤 Stops in ~5 mins' in screen.display[0])
                self.assertIn('Video0',screen.display[0])
                self.assertIn('50%',screen.display[0])
                queue.change('clear-stop',URLS[0]);header.due=0;header.update()
                wait(lambda _: '💤' not in screen.display[0])
                queue.change('remove',URLS[0]);header.due=0;header.update()
                wait(lambda _: 'Video0' not in screen.display[0])

    def test_header_avatar_stays_on_title_row_across_views_and_resize(self):
        import fcntl, os, pty, select, signal, struct, subprocess, termios, time
        import pyte
        import newsboat_thumbnails as thumbs
        from newsboat_playlist_avatars import parse_rows
        from test_newsboat_reconnect import BINARY
        with isolated() as (root,_):
            queue.change('add',URLS[0]);header=panel.Header();header.update()
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description><item><guid>1</guid><title>Article</title><link>https://example.org/a</link></item></channel></rss>')
            config=root/'config';config.write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\nfeedlist-title-format " Newsboat"\n')
            urls=root/'urls';urls.write_text(feed.as_uri()+'\n')
            cmd=[str(BINARY),'-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(cmd+['-x','reload'],capture_output=True,check=True)
            pid,fd=pty.fork()
            if pid==0:
                fcntl.ioctl(0,termios.TIOCSWINSZ,struct.pack('HHHH',20,120,1200,400))
                os.execve(str(BINARY),cmd,dict(os.environ,TERM='xterm-256color',NEWSBOAT_THUMBNAILS='1',NEWSBOAT_QUEUE_HEADER=str(header.path)))
            screen=pyte.Screen(120,20);stream=pyte.ByteStream(screen);decoder=thumbs.Decoder();rows=[]
            def check():
                nonlocal rows
                until=time.monotonic()+.4
                while time.monotonic()<until:
                    if select.select([fd],[],[],.02)[0]:
                        for kind,value in decoder.feed(os.read(fd,65536)):
                            if kind=='screen':stream.feed(value)
                            elif kind=='avatars':rows=parse_rows(value)
                avatar=next((r for r in rows if r[1]==0),None)
                self.assertIsNotNone(avatar)
                x,y,request=avatar
                self.assertEqual(screen.display[0].index('Video0'),x+3)
                self.assertNotIn('Creator',screen.display[0])
                self.assertEqual(request.split('\t')[:2],[URLS[0],'Creator'])
            try:
                check()
                os.write(fd,b'\n');check()
                os.write(fd,b'?');check()
                fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',20,100,1000,400));os.kill(pid,signal.SIGWINCH)
                screen.resize(20,100);check()
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

    def test_long_title_scrolls_in_compact_fixed_space_while_idle(self):
        with isolated() as (root,_):
            header=root/'header.tsv'
            title='ABCDEFGHIJ KLMNOPQRST UVWXYZ-end'
            header.write_text(title+'\tCreator\t━━━━──── 50% · 5:00 left\t'+URLS[0]+'\n')
            feed=root/'feed.xml';feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.org</link><description>Test</description></channel></rss>')
            cfg='show-read-feeds yes\nconfirm-exit no\nfeedlist-title-format " Newsboat"\n'
            with reader(root,cfg,feed.as_uri()+'\n',{'NEWSBOAT_QUEUE_HEADER':str(header)}) as (_,screen,send,wait):
                wait(lambda _: 'ABCDEFGHIJ' in screen.display[0])
                start=screen.display[0].index('ABCDEFGHIJ')
                self.assertGreaterEqual(start,71)
                suffix=screen.display[0].index('50%')
                wait(lambda _: 'XYZ-end' in screen.display[0],timeout=10)
                self.assertEqual(screen.display[0].index('50%'),suffix)
                self.assertNotIn('ABCDEFGHIJ',screen.display[0])
                self.assertIn('Newsboat',screen.display[0])
                header.write_text('New video\tCreator\t━━━━──── 50% · 5:00 left\t'+URLS[1]+'\n')
                wait(lambda _: 'New video' in screen.display[0])
