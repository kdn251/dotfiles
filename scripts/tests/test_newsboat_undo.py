"""Undo follows the changed item and restores purged Starred rows."""
import fcntl, json, os, pty, select, signal, sqlite3, struct, subprocess, tempfile, termios, time, unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte=None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.local/lib/newsboat-paged/newsboat'))

@unittest.skipUnless(pyte and BINARY.exists(),'requires native Newsboat and pyte')
class UndoTests(unittest.TestCase):
    def test_read_star_unstar_and_return_to_home(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);feed=root/'feed.xml';urls=root/'urls';cfg=root/'config'
            feed.write_text('<rss version="2.0"><channel><title>⭐ Starred</title><link>https://example.com</link><description>Test</description>'+''.join(f'<item><title>Item{i}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in range(1,4))+'</channel></rss>')
            urls.write_text(feed.as_uri()+'\n')
            cfg.write_text('show-read-articles yes\nshow-read-feeds yes\narticle-sort-order title-asc\narticlelist-format "%f %t"\nconfirm-exit no\nbind n articlelist toggle-article-read\nbind U everywhere undo-action\nbind s articlelist undo-checkpoint star ; toggle-article-read "read" "group"\nbind S articlelist undo-checkpoint unstar ; delete-article ; purge-deleted\n')
            helper=root/'restore.py';helper.write_text('import json,sys\nfrom pathlib import Path\nPath(__file__).with_name("restored").write_text(json.dumps(sys.argv[1:]))\n')
            args=[str(BINARY),'-q','-C',str(cfg),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(HOME=directory,TERM='xterm-256color',NEWSBOAT_UNDO_FILE=str(root/'undo'),NEWSBOAT_UNDO_HELPER=str(helper),NEWSBOAT_STARRED_STATUS=str(root/'stars'))
                os.execv(str(BINARY),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.02)[0]:stream.feed(os.read(fd,65536))
                    if predicate():return
                self.fail('\n'.join(screen.display))
            def has(text):return text in '\n'.join(screen.display)
            try:
                wait(lambda:has('Starred'));os.write(fd,b'\n');wait(lambda:has('Item3'))
                os.write(fd,b'n');wait(lambda:screen.cursor.y==2)
                os.write(fd,b'U');wait(lambda:screen.cursor.y==1 and has('Undid last'))
                self.assertIn('N',screen.display[1]);self.assertIn('Item1',screen.display[1])
                self.assertEqual(json.loads((root/'restored').read_text())[-2:],['keep','unread'])
                os.write(fd,b's');wait(lambda:screen.cursor.y==2)
                os.write(fd,b'U');wait(lambda:screen.cursor.y==1 and not (root/'undo').exists())
                self.assertEqual(json.loads((root/'restored').read_text())[-2:],['unstar','unread'])
                (root/'stars').write_text('https://example.com/1\n')
                os.write(fd,b'S');wait(lambda:not has('Item1'))
                self.assertTrue(screen.display[1].lstrip().startswith('1 '))
                self.assertIn('Item2',screen.display[1])
                os.write(fd,b'U');wait(lambda:has('Item1') and screen.cursor.y==1)
                self.assertTrue(screen.display[1].lstrip().startswith('1 '))
                self.assertTrue(screen.display[2].lstrip().startswith('2 '))
                self.assertEqual(json.loads((root/'restored').read_text())[-2:],['star','unread'])
                with sqlite3.connect(root/'cache') as db:
                    self.assertEqual(db.execute("SELECT unread,deleted FROM rss_item WHERE guid='1'").fetchone(),(1,0))
                os.write(fd,b'n');wait(lambda:screen.cursor.y==2)
                os.write(fd,b'q');wait(lambda:not has('Item1'))
                os.write(fd,b'U');wait(lambda:not (root/'undo').exists())
                os.write(fd,b'\n');wait(lambda:has('Item1'))
                self.assertIn('N',screen.display[1])
                os.write(fd,b'U');wait(lambda:has('Nothing to undo'))
            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
