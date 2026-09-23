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
            config.write_text('article-sort-order title-desc\nshow-read-feeds yes\nshow-read-articles yes\nprepopulate-query-feeds yes\nconfirm-exit no\narticlelist-format "%t"\n')
            feed.write_text('<rss version="2.0"><channel><title>Source</title><link>https://example.com</link><description>Test</description>'+''.join(f'<item><title>Video{i:02}</title><link>https://example.com/{i}</link><guid>{i}</guid></item>' for i in [3,7,1,5,2,6,4])+'</channel></rss>')
            remaining = list(range(1,8))
            def update():
                expr = ' or '.join(f'title = "Video{i:02}"' for i in remaining) or 'title = "none"'
                temporary=root/'urls.new'
                temporary.write_text('"query:📥 Downloads:'+expr.replace('"','\\"')+'"\n'+feed.as_uri()+'\n')
                temporary.replace(urls)
            update()
            args=[str(BINARY),'-q','-C',str(config),'-u',str(urls),'-c',str(root/'cache')]
            subprocess.run(args+['-x','reload'],check=True,capture_output=True)
            pid,fd=pty.fork()
            if pid==0:
                os.environ.update(TERM='xterm-256color',HOME=folder,NEWSBOAT_DOWNLOAD_STATUS=str(root/'status.tsv'))
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
                os.write(fd,b':3\n')
                wait(lambda:selected('Video05'))
                # Ordinary refresh must not advance the cursor.
                reload()
                time.sleep(.2)
                wait(lambda:selected('Video05'))
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
                (root/'status.tsv.watched').write_text('')
                wait(lambda:order()==['07','03','02'] and selected('Video03'))

            finally:
                os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)
