"""Real-terminal visual selection, bulk mutation and search regression tests."""
from contextlib import contextmanager
import fcntl,os,pty,select,signal,sqlite3,struct,subprocess,tempfile,termios,time,unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte=None
BINARY=Path(os.environ.get('NEWSBOAT_PAGED_BINARY',Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat'))

@contextmanager
def session(extra='', query=False):
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory);feed=root/'feed.xml';config=root/'config';urls=root/'urls'
        feed.write_text('<rss version="2.0"><channel><title>⭐ Starred</title><link>https://example.org</link><description>Test</description>'+''.join(f'<item><title>Item{i:02}</title><link>https://example.org/{i}</link><guid>{i}</guid><author>Channel{i}</author><description>Body needle{i}</description></item>' for i in range(1,31))+'</channel></rss>')
        urls.write_text(('"query:📥 Downloads:title != \\\"\\\""\n' if query else '')+feed.as_uri()+'\n')
        helper=root/'delete-downloaded.sh'
        helper.write_text('#!/usr/bin/env python3\nimport sys,json\nfrom pathlib import Path\np=Path(__file__).parent\nwith (p/"actions").open("a") as f:f.write(sys.argv[1]+"\\n")\n'+('''url=sys.argv[1]
with (p/'removed').open('a') as f:f.write(url+'\\n')
removed=set((p/'removed').read_text().splitlines())
expr=' or '.join('link = "https://example.org/%s"'%i for i in range(1,31) if 'https://example.org/%s'%i not in removed) or 'title = "none"'
(p/'urls').write_text('"query:📥 Downloads:'+expr.replace('"','\\\\"')+'"\\n'+(p/'feed.xml').as_uri()+'\\n')
''' if query else ''))
        restore=root/'restore-download.py'
        restore.write_text("""import sys
from pathlib import Path
p=Path(__file__).parent
removed=set((p/'removed').read_text().splitlines());removed.discard(sys.argv[2])
(p/'removed').write_text('\\n'.join(removed))
expr=' or '.join('link = "https://example.org/%s"'%i for i in range(1,31) if 'https://example.org/%s'%i not in removed)
(p/'urls').write_text('"query:📥 Downloads:'+expr.replace('"','\\\\"')+'"\\n'+(p/'feed.xml').as_uri()+'\\n')
""")
        helper.chmod(0o755)
        action=root/'action.py';action.write_text(helper.read_text());action.chmod(0o755)
        config.write_text('show-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nconfirm-exit no\narticle-sort-order title-asc\narticlelist-format "%f %a %t"\ncolor listfocus black cyan bold\ncolor listfocus_unread black cyan bold\nscrolloff 5\nbind-key j down\nbind-key k up\nbind V articlelist,searchresultslist visual-rows\nbind ESC articlelist,searchresultslist visual-cancel\nbind n articlelist toggle-article-read\nbind U everywhere undo-action\n'+f'bind f articlelist,searchresultslist undo-checkpoint favorites ; set browser "{action} %u" ; open-in-browser-noninteractively ; set browser "true"\n'+f'bind S articlelist,searchresultslist undo-checkpoint unstar ; set browser "{action} %u" ; open-in-browser-noninteractively ; set browser "true" ; delete-article ; purge-deleted\n'+f'macro D set browser "{helper} %u" ; open-in-browser-noninteractively ; set browser "true" ; reload-urls\n'+extra)
        (root/'undo-helper.py').write_text('pass\n')
        args=[str(BINARY),'-l','6','-d',str(root/'debug.log'),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
        subprocess.run(args+['-x','reload'],check=True,capture_output=True)
        pid,fd=pty.fork()
        if pid==0:
            os.environ.update(TERM='xterm-256color',HOME=directory,NEWSBOAT_UNDO_FILE=str(root/'undo'),NEWSBOAT_UNDO_HELPER=str(root/'undo-helper.py'),NEWSBOAT_DOWNLOAD_UNDO_HELPER=str(restore),NEWSBOAT_FAVORITES_HELPER=str(root/'undo-helper.py'),NEWSBOAT_DOWNLOAD_STATUS=str(root/'status'))
            os.execv(str(BINARY),args)
        fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',14,110,0,0))
        screen=pyte.Screen(110,14);stream=pyte.ByteStream(screen)
        def wait(predicate):
            end=time.monotonic()+6
            while time.monotonic()<end:
                if select.select([fd],[],[],.03)[0]:
                    try:stream.feed(os.read(fd,65536))
                    except OSError:raise AssertionError((root/'urls').read_text()+'\n'+'\n'.join(screen.display)+'\n'+(root/'debug.log').read_text()[-1500:])
                if predicate():return
            raise AssertionError('\n'.join(screen.display)+'\n'+'\n'.join(line for line in (root/'debug.log').read_text().splitlines() if 'event =' in line)[-800:])
        def send(keys):os.write(fd,keys.encode())
        try:
            wait(lambda:'Starred' in '\n'.join(screen.display));time.sleep(.2);send('\n');wait(lambda:'Item01' in '\n'.join(screen.display))
            yield root,screen,send,wait
        finally:
            os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

@unittest.skipUnless(pyte and BINARY.exists(), 'requires pyte and native Newsboat')
class VisualRowsTests(unittest.TestCase):
    def test_range_shrinks_reverses_crosses_page_and_cancels(self):
        with session() as (root,screen,send,wait):
            title_before=screen.display[0]
            def highlighted(title):
                rows=[i for i,line in enumerate(screen.display) if title in line]
                return bool(rows) and screen.buffer[rows[0]][90].bg=='cyan'
            send('jjVjj');wait(lambda:'Item05' in screen.display[screen.cursor.y] and highlighted('Item03'))
            self.assertEqual(screen.display[0],title_before)
            for title in ('Item03','Item04','Item05'):
                row=next(i for i,line in enumerate(screen.display) if title in line)
                self.assertEqual(screen.buffer[row][90].bg,'cyan')
            send('k');wait(lambda:'Item04' in screen.display[screen.cursor.y] and not highlighted('Item05'))
            row=next(i for i,line in enumerate(screen.display) if 'Item05' in line)
            self.assertNotEqual(screen.buffer[row][90].bg,'cyan')
            send('kk');wait(lambda:highlighted('Item03') and 'Item02' in screen.display[screen.cursor.y])
            send('j'*20);wait(lambda:'Item22' in screen.display[screen.cursor.y] and highlighted('Item21'))
            send('\x1b');wait(lambda:not highlighted('Item21'))
            self.assertEqual(screen.display[0],title_before)
            self.assertIn('Item22',screen.display[screen.cursor.y])

    def test_bulk_favorites_and_unstar_keep_exact_targets(self):
        with session() as (root,screen,send,wait):
            send('jVjjf');wait(lambda:(root/'actions').exists() and len((root/'actions').read_text().splitlines())==3 and 'Applied action to 3' in '\n'.join(screen.display) and 'Item05' in screen.display[screen.cursor.y])
            self.assertEqual((root/'actions').read_text().splitlines(),[f'https://example.org/{i}' for i in (2,3,4)])
            self.assertIn('Item05',screen.display[screen.cursor.y])
            send('VjjS');wait(lambda:'Applied action to 3' in '\n'.join(screen.display) and 'Item08' in screen.display[screen.cursor.y])
            self.assertEqual((root/'actions').read_text().splitlines()[-3:],[f'https://example.org/{i}' for i in (5,6,7)])
            for title in ('Item05','Item06','Item07'):self.assertNotIn(title,'\n'.join(screen.display))
            send('U');wait(lambda:'Undid bulk action (3 rows)' in '\n'.join(screen.display) and all(title in '\n'.join(screen.display) for title in ('Item05','Item06','Item07')))
            for title in ('Item05','Item06','Item07'):self.assertIn(title,'\n'.join(screen.display))

    def test_macro_delete_uses_snapshot_as_query_shrinks(self):
        with session(query=True) as (root,screen,send,wait):
            send('jVjj,D');wait(lambda:(root/'actions').exists() and len((root/'actions').read_text().splitlines())==3 and 'Item05' in screen.display[screen.cursor.y])
            self.assertEqual((root/'actions').read_text().splitlines(),[f'https://example.org/{i}' for i in (2,3,4)])
            for title in ('Item02','Item03','Item04'):self.assertNotIn(title,'\n'.join(screen.display))
            send('U');wait(lambda:'Undid bulk action (3 rows)' in '\n'.join(screen.display) and all(title in '\n'.join(screen.display) for title in ('Item02','Item03','Item04')))
            self.assertEqual((root/'removed').read_text(),'')

    def test_search_results_select_and_bulk_apply(self):
        with session() as (root,screen,send,wait):
            send('/Item0\n');wait(lambda:'Search' in screen.display[0] and 'Item01' in '\n'.join(screen.display))
            send('Vjf');wait(lambda:(root/'actions').exists() and len((root/'actions').read_text().splitlines())==2)
            self.assertEqual((root/'actions').read_text().splitlines(),[f'https://example.org/{i}' for i in (1,2)])

    def test_search_finds_channel_and_read_items(self):
        with session() as (root,screen,send,wait):
            send('n');wait(lambda:'Item02' in screen.display[screen.cursor.y])
            send('/Channel1\n');wait(lambda:'Search' in screen.display[0] and 'Item01' in '\n'.join(screen.display))
            self.assertNotIn('Item02','\n'.join(screen.display))
            send('q/needle1\n');wait(lambda:'needle1' in screen.display[0] and 'Item01' in '\n'.join(screen.display))
