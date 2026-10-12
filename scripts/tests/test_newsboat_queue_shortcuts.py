"""Global Queue playback shortcuts work without a selected article."""
import tempfile
import unittest
from pathlib import Path
from test_newsboat_reconnect import reader

class QueueShortcutTests(unittest.TestCase):
 def test_global_play_and_play_show_without_reopening_queue(self):
  for in_queue in (False, True):
   with self.subTest(in_queue=in_queue), tempfile.TemporaryDirectory() as folder:
    root=Path(folder); scripts=root/'scripts';scripts.mkdir();called=root/'called'
    (scripts/'newsboat_queue.py').write_text('from pathlib import Path\nimport sys\nwith Path('+repr(str(called))+').open("a") as f:f.write(sys.argv[1]+"\\n")\n')
    config=Path(__file__).resolve().parents[2]/'newsboat/.newsboat/config'
    bindings='\n'.join(l for l in config.read_text().splitlines() if l.startswith(('bind w ','bind W ')))
    cfg='show-read-feeds yes\nconfirm-exit no\nprepopulate-query-feeds yes\nfeedlist-format "%t"\nbind ? everywhere help\n'+bindings+'\n'
    env={'NEWSBOAT_QUEUE_VIEW':'1'} if in_queue else {}
    with reader(root,cfg,'"query:📬 New:link = \\"placeholder\\""\n',env) as (_,screen,send,wait):
     wait(lambda s:'New' in s)
     send('w');wait(lambda s:called.exists())
     self.assertEqual(called.read_text().splitlines(),['resume'])
     self.assertIn('feeds',screen.display[0].lower())
     send('W');wait(lambda s:len(called.read_text().splitlines())==(2 if in_queue else 3))
     self.assertEqual(called.read_text().splitlines(),['resume','ensure-playing']+([] if in_queue else ['show']))
     send('?');wait(lambda s:'Help' in s)
     send('w');wait(lambda s:len(called.read_text().splitlines())==(3 if in_queue else 4))
     self.assertEqual(called.read_text().splitlines()[-1],'resume')
     self.assertIn('Help','\n'.join(screen.display))

class QueuePlayerDetectionTests(unittest.TestCase):
 def test_live_queue_and_startup_worker_only(self):
  import newsboat_queue as queue
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);process=root/'123';process.mkdir()
   for args,env,expected in [
    (b'mpv\0video.mp4\0',b'NEWSBOAT_QUEUE_PLAYBACK=1\0',True),
    (b'mpv\0video.mp4\0',b'',False),
    (b'python3\0/tmp/newsboat-play-video.py\0--wait\0url\0',b'NEWSBOAT_QUEUE_PLAYBACK=1\0',True),
    (b'python3\0/tmp/newsboat_queue.py\0ensure-playing\0',b'NEWSBOAT_QUEUE_PLAYBACK=1\0',False)]:
    (process/'cmdline').write_bytes(args);(process/'environ').write_bytes(env)
    self.assertEqual(queue.queue_player_running(root),expected)
   (process/'cmdline').unlink()
   self.assertFalse(queue.queue_player_running(root))
 def test_ensure_does_not_restart_existing_player(self):
  import newsboat_queue as queue
  from unittest.mock import patch
  with patch.object(queue,'queue_player_running',return_value=True) as running, patch.object(queue,'resume',return_value=0) as resume:
   self.assertEqual(queue.ensure_playing(),0);resume.assert_not_called()
   running.return_value=False
   self.assertEqual(queue.ensure_playing(),0);resume.assert_called_once()
