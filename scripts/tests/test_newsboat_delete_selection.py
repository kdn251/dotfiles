"""Native Downloads reload must retain display order and adjacent selection."""
import fcntl
import os
import pty
import select
import signal
import struct
import subprocess
import tempfile
import termios
import time
import unittest
from pathlib import Path
try:
    import pyte
except ImportError:
    pyte = None
BINARY = Path(os.environ.get('NEWSBOAT_PAGED_BINARY', Path.home()/'.local/lib/newsboat-paged/newsboat'))


@unittest.skipUnless(pyte and BINARY.exists(), 'requires pyte and native Newsboat')
class DeleteSelectionTests(unittest.TestCase):
    def test_reload_delete_middle_last_and_filtered_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config, urls, feed = root/'config', root/'urls', root/'feed.xml'
            config.write_text('article-sort-order title-desc\nshow-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nconfirm-exit no\ncolor listfocus black cyan bold\ncolor listfocus_unread black cyan bold\nhighlight articlelist ".*📌.*" cyan default bold\narticlelist-format "%p %t"\n')
            editor = root/'editor.py'
            editor.write_text('import sys\nfrom pathlib import Path\nPath(sys.argv[1]).write_text("Notes from the editor\\n")\n')
            with config.open('a') as output:
                helper = Path(__file__).resolve().parents[1]/'scripts/newsboat-notes.py'
                output.write(f'bind I articlelist set browser "python3 {helper} %u" ; open-in-browser ; set browser "true"\n')
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description>'+''.join(f'<item><title>Video{i:02}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in [3,7,1,5,2,6,4])+'</channel></rss>')
            feed.write_text(feed.read_text().replace('https://example.com/1</link>', 'https://youtu.be/abc123DEF45</link>'))
            remaining = list(range(1,8))
            def update():
                expr = ' or '.join(f'title = "Video{i:02}"' for i in remaining) or 'title = "none"'
                temporary=root/'urls.new'
                temporary.write_text('"query:📥 Downloads:'+expr.replace('"','\\"')+'"\n'+feed.as_uri()+'\n')
                temporary.replace(urls)
            update()
            (root/'status.tsv.order').write_text(''.join(f'https://example.com/{i}\t{i*100}\n' for i in remaining))
            args=[str(BINARY),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(TERM='xterm-256color',HOME=folder,NEWSBOAT_DOWNLOAD_STATUS=str(root/'status.tsv'),NEWSBOAT_LAST_OPENED=str(root/'last-opened'),NEWSBOAT_NOTES_STATUS=str(root/'noted-urls'),XDG_DATA_HOME=str(root/'data'),VISUAL='python3 '+str(editor))
                os.execv(str(BINARY),args)
            fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',24,100,0,0))
            screen=pyte.Screen(100,24);stream=pyte.ByteStream(screen)
            def wait(predicate):
                deadline=time.monotonic()+5
                while time.monotonic()<deadline:
                    if select.select([fd],[],[],.05)[0]:stream.feed(os.read(fd,65536))
                    if predicate():return
                self.fail('\n'.join(screen.display))
            def selected(title):return title in screen.display[screen.cursor.y]
            def reload():os.write(fd,b':exec reload-urls\n')
            try:
                wait(lambda:'Downloads' in '\n'.join(screen.display))
                os.write(fd,b':1\n\n')
                wait(lambda:selected('Video07'))
                self.assertIn('0%', screen.display[1])
                self.assertIn('0%', screen.display[7])
                os.write(fd,b':3\n')
                wait(lambda:selected('Video05'))
                # Ordinary refresh must not advance the cursor.
                reload()
                time.sleep(.2)
                wait(lambda:selected('Video05'))
                # Deletion publishes status before reload-urls runs. Losing
                # the removed row's timestamp must not send it to the bottom
                # and change which row counts as its next neighbour.
                (root/'status.tsv.order').write_text(''.join(f'https://example.com/{i}\t{i*100}\n' for i in remaining if i != 5))
                time.sleep(1.2)
                os.write(fd,b':exec redraw\n')
                time.sleep(.2)
                wait(lambda:selected('Video05') and 'Video05' in screen.display[3])
                remaining.remove(5);update();reload()
                wait(lambda:'Video05' not in '\n'.join(screen.display) and selected('Video04'))
                displayed=[line.split('Video')[1][:2] for line in screen.display if 'Video' in line]
                self.assertEqual(displayed,['07','06','04','03','02','01'])
                # End-of-list removal chooses the previous survivor.
                os.write(fd,b':6\n');wait(lambda:selected('Video01'))
                remaining.remove(1);update();reload()
                wait(lambda:'Video01' not in '\n'.join(screen.display) and selected('Video02'))
                # If concurrent cleanup removes the immediate neighbour too,
                # choose the next surviving row, rather than jumping to top.
                os.write(fd,b':2\n');wait(lambda:selected('Video06'))
                remaining.remove(6);remaining.remove(4);update();reload()
                wait(lambda:'Video06' not in '\n'.join(screen.display) and selected('Video03'))
                # Watch progress sorts descending; ties use download time,
                # independently of article publication order or title.
                (root/'status.tsv.order').write_text('https://example.com/7\t700\nhttps://example.com/3\t300\nhttps://example.com/2\t200\n')
                (root/'status.tsv.watched').write_text('https://example.com/2\t80%\nhttps://example.com/3\t30%\n')
                def order():
                    return [line.split('Video')[1][:2] for line in screen.display if 'Video' in line]
                wait(lambda:order()==['02','03','07'] and selected('Video03'))
                (root/'status.tsv.watched').write_text('https://example.com/7\t100%\nhttps://example.com/2\t80%\nhttps://example.com/3\t30%\n')
                wait(lambda:order()==['07','02','03'] and selected('Video03'))
                # Active and failed downloads stay above even fully watched files.
                (root/'status.tsv').write_text('https://example.com/3\t↓ 42%\n')
                wait(lambda:order()==['03','07','02'] and selected('Video03'))
                (root/'status.tsv').write_text('https://example.com/3\t✕\n')
                wait(lambda:order()==['03','07','02'] and '✕' in '\n'.join(screen.display))
                (root/'status.tsv').write_text('https://example.com/3\t…\n')
                wait(lambda:order()==['03','07','02'] and '…' in '\n'.join(screen.display))
                (root/'status.tsv').write_text('https://example.com/3\t📥\n')
                wait(lambda:order()==['07','02','03'] and selected('Video03'))
                (root/'status.tsv.watched').write_text('')
                wait(lambda:order()==['07','03','02'] and selected('Video03'))

                (root/'status.tsv.read').write_text('https://example.com/3\t65%\n')
                wait(lambda:any('65%' in row and 'Video03' in row for row in screen.display))
                self.assertTrue(selected('Video03'))
                (root/'status.tsv.read').write_text('')
                wait(lambda:order()==['07','03','02'])

                # Opening an article marks it even after returning and moving
                # away. An external browser/player open replaces the marker.
                os.write(fd,b'\n')
                wait(lambda:(root/'last-opened').exists())
                self.assertEqual((root/'last-opened').read_text().strip(),'https://example.com/3')
                os.write(fd,b'q')
                wait(lambda: any('📌' in row and 'Video03' in row for row in screen.display))
                row = next(i for i,line in enumerate(screen.display) if '📌' in line and 'Video03' in line)
                column = screen.display[row].index('Video03')
                self.assertEqual(screen.buffer[row][column].fg, 'black')
                self.assertEqual(screen.buffer[row][column].bg, 'cyan')
                os.write(fd,b':1\n')
                wait(lambda:selected('Video07'))
                self.assertTrue(any('📌' in row and 'Video03' in row for row in screen.display))
                self.assertEqual(screen.buffer[row][column].fg, 'cyan')

                (root/'last-opened').write_text('https://example.com/2\n')
                wait(lambda:any('📌' in row and 'Video02' in row for row in screen.display))
                self.assertTrue(selected('Video07'))
                self.assertFalse(any('📌' in row and 'Video03' in row for row in screen.display))

                (root/'noted-urls').write_text('https://example.com/3\n')
                wait(lambda:any('📝' in row and 'Video03' in row for row in screen.display))
                self.assertTrue(selected('Video07'))
                (root/'noted-urls').write_text('')
                wait(lambda:all('📝' not in row for row in screen.display))
                self.assertTrue(selected('Video07'))

                os.write(fd,b'I')
                wait(lambda:any('📝' in row and 'Video07' in row for row in screen.display))
                self.assertTrue(selected('Video07'))
                note_files = list((root/'data/newsboat/notes').glob('*.txt'))
                self.assertEqual(len(note_files),1)
                self.assertEqual(note_files[0].read_text(),'Notes from the editor\n')

            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
