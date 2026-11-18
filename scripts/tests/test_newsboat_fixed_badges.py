"""Live status changes keep a fixed metadata/title origin."""
import unittest

class FixedBadgeTests(unittest.TestCase):
    def test_live_queue_download_and_overflow_preserve_columns(self):
        from pathlib import Path
        import tempfile,subprocess,os,pty,fcntl,termios,struct,time,select,re,signal
        binary=str(Path.home()/'.cache/newsboat-paged/newsboat-r2.44/newsboat')
        if not Path(binary).exists():self.skipTest('Custom Newsboat build unavailable')
        with tempfile.TemporaryDirectory() as d:
         p=Path(d);url='https://www.youtube.com/watch?v=aaaaaaaaaaa'
         (p/'feed.xml').write_text('<rss version="2.0"><channel><title>Test</title><link>https://example.org</link><description>Test</description><item><title>Stable title</title><author>Creator</author><link>'+url+'</link><guid>'+url+'</guid></item></channel></rss>')
         (p/'urls').write_text((p/'feed.xml').as_uri()+'\n');(p/'queue').write_text('');(p/'downloads').write_text('')
         (p/'config').write_text('show-read-feeds yes\nshow-read-articles yes\nconfirm-exit no\narticlelist-format "|%-1p|%a|%t"\nrun-on-startup open\n')
         args=[binary,'-q','-C',str(p/'config'),'-u',str(p/'urls'),'-c',str(p/'cache')];subprocess.run(args+['-x','reload'],check=True,capture_output=True)
         pid,fd=pty.fork()
         if pid==0:
          os.environ.update(TERM='xterm-256color',NEWSBOAT_QUEUE_STATUS=str(p/'queue'),NEWSBOAT_DOWNLOAD_STATUS=str(p/'downloads'));os.execv(binary,args)
         fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',20,120,0,0))
         def wait(expected):
          data=b'';until=time.monotonic()+5
          while time.monotonic()<until:
           os.write(fd,b'\x0c')
           if select.select([fd],[],[],.1)[0]:data+=os.read(fd,65536)
           time.sleep(.05)
           text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',data.decode(errors='replace'))
           if expected in text:return
          raise AssertionError(repr(text[-1800:]))
         try:
          wait('|         |Creator|Stable title')
          (p/'queue').write_text(url+'\ttoken\n');wait('|📺       |Creator|Stable title')
          (p/'downloads').write_text(url+'\t📥\n');wait('|📺 📥    |Creator|Stable title')
          (p/'queue').write_text('');wait('|📥       |Creator|Stable title')
          (p/'downloads').write_text('');wait('|         |Creator|Stable title')
          (p/'downloads').write_text(url+'\tabcdefghijklmnopqrst\n');wait('|abcdefgh…|Creator|Stable title')
         finally:os.kill(pid,signal.SIGTERM);os.waitpid(pid,0);os.close(fd)

if __name__ == "__main__":unittest.main()
