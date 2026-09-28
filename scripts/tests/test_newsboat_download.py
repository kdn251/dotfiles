"""Offline downloader lifecycle, notification, and Waybar regression checks."""
import importlib.util
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('downloads', SCRIPTS / 'newsboat-download.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
URL = 'https://www.youtube.com/watch?v=abc123DEF45'
TITLE = '''A creator's "great" video & $(touch SHOULD_NOT_EXIST)'''

FAKE_YTDLP = r'''#!/usr/bin/python3
import json,os,sys,time
from pathlib import Path
args=sys.argv[1:]
with open(os.environ['CALLS'],'a') as f:f.write(json.dumps(args)+'\n')
mode=os.environ.get('FAIL','')
if Path(os.environ['CALLS']+'.retried').exists():mode=''
if '--dump-single-json' in args:
 if mode in ('bot','bot_always') and (mode=='bot_always' or '--cookies-from-browser' not in args):
  print('Sign in to confirm you are not a bot',file=sys.stderr);sys.exit(1)
 if mode=='metadata':
  print('HTTP 403: deliberate metadata failure',file=sys.stderr);sys.exit(1)
 twitch='twitch.tv' in args[-1]
 print(json.dumps(dict(id='1234567890' if twitch else 'abc123DEF45',title=os.environ['TITLE'],
                       channel='Creator',channel_id='UCtest',uploader_id='creator')))
 sys.exit(0)
assert '--load-info-json' in args and '--no-simulate' in args
folder=Path(args[args.index('-o')+1]).parent
folder.mkdir(parents=True,exist_ok=True)
partial=folder/'video [abc123DEF45].mp4.part'
if partial.exists():
 assert '--continue' in args
 Path(os.environ['CALLS']+'.resumed').touch()
partial.write_bytes(b'partial-video')
for amount in (10,60,100):
 print('NBPROGRESS:'+json.dumps(dict(downloaded_bytes=amount,total_bytes=100)),flush=True)
 time.sleep(float(os.environ.get('DELAY','0.03')))
if mode=='twice':
 attempts=Path(os.environ['CALLS']+'.attempts')
 count=int(attempts.read_text())+1 if attempts.exists() else 1
 attempts.write_text(str(count))
 if count<3:
  print('temporary failure',file=sys.stderr);sys.exit(1)
if mode=='download':
 print('HTTP 403: deliberate download failure',file=sys.stderr);sys.exit(1)
if mode!='missing':
 target=folder/'video [abc123DEF45].mp4';target.write_bytes(b'finished-video')
 partial.unlink(missing_ok=True)
 outputs=Path(args[args.index('--print-to-file')+2])
 outputs.write_text(json.dumps(str(target))+'\n')
'''
FAKE_NOTIFY = r'''#!/usr/bin/python3
import json,os,sys
with open(os.environ['NOTICES'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\n')
print(73)
if os.environ.get('AUTO_RETRY') and 'Download failed' in sys.argv:
 from pathlib import Path
 marker=Path(os.environ['CALLS']+'.retried')
 if not marker.exists():
  marker.touch();print('retry')
'''


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        bin_dir = self.root / '.local/bin'
        bin_dir.mkdir(parents=True)
        notify_dir = self.root / 'test-bin'
        notify_dir.mkdir()
        for name, content in [('yt-dlp', FAKE_YTDLP), ('notify-send', FAKE_NOTIFY)]:
            file = (bin_dir if name == 'yt-dlp' else notify_dir) / name
            file.write_text(content)
            file.chmod(0o755)
        for cache in ('.cache/yt-channel-avatars/UCtest.png', '.cache/twitch-profiles/creator.png'):
            file = self.root / cache
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(b'cached-avatar')
        self.env = dict(os.environ, HOME=str(self.root), XDG_STATE_HOME=str(self.root/'state'),
                        NEWSBOAT_VIDEO_DIR=str(self.root/'videos'), TITLE=TITLE,
                        CALLS=str(self.root/'calls'), NOTICES=str(self.root/'notices'),
                        NEWSBOAT_DOWNLOAD_ATTEMPTS='1', NEWSBOAT_DOWNLOAD_RETRY_DELAYS='0.01,0.01',
                        PATH=f'{notify_dir}:/usr/bin:/bin')  # No ~/.local/bin, like the desktop.
        self.processes = []

    def tearDown(self):
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
            p.wait(timeout=5)
        self.temp.cleanup()

    def command(self, *args):
        return ['python3', str(SCRIPTS/'newsboat-download.py'), *args]

    def start(self, url=URL, **extra):
        p = subprocess.Popen(self.command(url), env=dict(self.env, **extra))
        self.processes.append(p)
        return p

    def state(self, url=URL):
        key = module.job_key(module.canonical_url(url)[1])
        return json.loads((self.root/f'state/newsboat/downloads/{key}.json').read_text())

    def wait_active(self, url=URL):
        end = time.monotonic()+5
        while time.monotonic()<end:
            try:
                if self.state(url)['status']=='downloading':return
            except FileNotFoundError:pass
            time.sleep(.02)
        self.fail('Download did not start')

    def read_notices(self):
        return [json.loads(line) for line in (self.root/'notices').read_text().splitlines()]

    def waybar(self):
        r = subprocess.run(self.command('--waybar'), env=self.env, capture_output=True, text=True, check=True)
        return json.loads(r.stdout)

    def test_youtube_success_avatar_title_and_completed_waybar(self):
        p = self.start()
        self.assertEqual(p.wait(timeout=5),0)
        job = self.state()
        self.assertEqual(job['status'],'done')
        self.assertGreater(Path(job['files'][0]).stat().st_size,0)
        notices = self.read_notices()
        for args in notices:
            title = f'{args[1]}: {TITLE}'
            self.assertEqual(args[-2:],['--',title])
            self.assertEqual(args[args.index('-i')+1],str(self.root/'.cache/yt-channel-avatars/UCtest.png'))
        self.assertEqual(notices[0][notices[0].index('-r')+1], '0')
        self.assertEqual(notices[-1][notices[-1].index('-r')+1], '73')
        self.assertEqual(self.waybar()['class'],'done')
        self.assertIn('Complete',self.waybar()['tooltip'])
        self.assertFalse((self.root/'SHOULD_NOT_EXIST').exists())
        self.assertEqual(notices[-1][-1], f'Download complete: {TITLE}')
        # Age the completion without sleeping; expired successes must hide.
        job['updated'] = time.time() - module.FINISHED_SECONDS - 1
        (self.root/f'state/newsboat/downloads/{job["key"]}.json').write_text(json.dumps(job))
        self.assertEqual(self.waybar(), {'text': ''})

    def test_failed_and_missing_output_never_report_complete(self):
        for mode in ('metadata','download','missing'):
            before = len(self.read_notices()) if (self.root/'notices').exists() else 0
            p = self.start(FAIL=mode)
            self.assertEqual(p.wait(timeout=5),1)
            end = time.monotonic()+3
            expected = before + (1 if mode == 'metadata' else 2)
            while time.monotonic() < end:
                if (self.root/'notices').exists() and len(self.read_notices()) >= expected:break
                time.sleep(.02)
            job = self.state()
            self.assertEqual(job['status'],'failed')
            self.assertEqual(self.read_notices()[-1][1],'Download failed')
            self.assertEqual(self.waybar()['class'],'failed')
            self.assertEqual(self.waybar()['text'],'✕')
            notice = self.read_notices()[-1]
            self.assertEqual(notice[notice.index('-u')+1], 'normal')
            self.assertEqual(notice[notice.index('-t')+1], '5000')
            if mode!='missing':
                self.assertIn('HTTP 403',Path(job['log']).read_text())
            job['updated'] = time.time() - module.FAILED_SECONDS - 1
            (self.root/f'state/newsboat/downloads/{job["key"]}.json').write_text(json.dumps(job))
            self.assertEqual(self.waybar(), {'text': ''})

    def test_concurrent_platforms_progress_duplicate_and_cancel(self):
        twitch='https://www.twitch.tv/videos/1234567890'
        youtube = self.start(DELAY='1')
        other = self.start(twitch, DELAY='1')
        self.wait_active()
        self.wait_active(twitch)
        state = self.waybar()
        self.assertEqual(state['class'],'downloading')
        self.assertIn('2',state['text'])
        self.assertIn('Downloading',state['tooltip'])
        duplicate=self.start('https://youtu.be/abc123DEF45?si=tracking')
        self.assertEqual(duplicate.wait(timeout=5),0)
        calls=[json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        self.assertEqual(sum('--dump-single-json' in args for args in calls),2)
        result=subprocess.run(self.command('--cancel-url',URL),env=self.env)
        self.assertEqual(result.returncode,0)
        self.assertEqual(youtube.wait(timeout=5),130)
        self.assertEqual(self.state()['status'],'cancelled')
        self.assertEqual(other.wait(timeout=5),0)
        self.assertEqual(self.state(twitch)['status'],'done')
        self.assertEqual(self.state(twitch)['icon'],str(self.root/'.cache/twitch-profiles/creator.png'))
        self.assertIn('twitch-vods/manual',self.state(twitch)['files'][0])

    def test_retry_action_restarts_the_same_video(self):
        p = self.start(FAIL='download', AUTO_RETRY='1')
        self.assertEqual(p.wait(timeout=5), 1)
        end = time.monotonic()+8
        while time.monotonic() < end:
            if self.state()['status'] == 'done':break
            time.sleep(.03)
        self.assertEqual(self.state()['status'], 'done')
        calls=[json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        urls=[args[-1] for args in calls if '--dump-single-json' in args]
        self.assertEqual(urls, [URL, URL])
        failed=next(n for n in self.read_notices() if n[1] == 'Download failed')
        self.assertIn('retry=Retry', failed)

    def test_youtube_challenge_retries_once_and_download_uses_same_session(self):
        p=self.start(FAIL='bot')
        self.assertEqual(p.wait(timeout=5),0)
        self.assertEqual(self.state()['status'],'done')
        calls=[json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        self.assertEqual(len(calls),3)
        self.assertNotIn('--cookies-from-browser',calls[0])
        for args in calls[1:]:
            self.assertEqual(args[args.index('--cookies-from-browser')+1],'brave+gnomekeyring')
        self.assertEqual(module.cookie_retry_options('twitch','not a bot'),[])
        self.assertEqual(module.cookie_retry_options('youtube','Private video'),[])

    def test_failed_authentication_does_not_retry_indefinitely(self):
        p=self.start(FAIL='bot_always')
        self.assertEqual(p.wait(timeout=5),1)
        calls=[json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        self.assertEqual(len(calls),2)
        self.assertIn('sign-in retry failed',self.state()['error'])

    def test_automatic_retries_succeed_on_third_attempt(self):
        p = self.start(FAIL='twice', NEWSBOAT_DOWNLOAD_ATTEMPTS='3')
        self.assertEqual(p.wait(timeout=8), 0)
        self.assertTrue(Path(self.env['CALLS']+'.resumed').exists())
        self.assertEqual(self.state()['attempt'], 3)
        self.assertEqual(self.state()['status'], 'done')
        notices = self.read_notices()
        self.assertFalse(any(n[1] == 'Download failed' for n in notices))
        calls = [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        downloads = [args for args in calls if '--load-info-json' in args]
        self.assertEqual(len(downloads), 3)
        self.assertTrue(all('--continue' in args for args in downloads))
        self.assertEqual(len({args[args.index('-o')+1] for args in downloads}), 1)

    def test_automatic_retries_stop_after_three_attempts(self):
        p = self.start(FAIL='download', NEWSBOAT_DOWNLOAD_ATTEMPTS='3')
        self.assertEqual(p.wait(timeout=8), 1)
        self.assertEqual(self.state()['status'], 'failed')
        self.assertEqual(self.state()['attempt'], 3)
        calls = [json.loads(line) for line in (self.root/'calls').read_text().splitlines()]
        self.assertEqual(sum('--load-info-json' in args for args in calls), 3)

    def test_interrupted_worker_can_resume(self):
        p = self.start(DELAY='1')
        self.wait_active()
        original = self.state()
        p.send_signal(signal.SIGHUP)
        self.assertEqual(p.wait(timeout=5), 130)
        self.assertEqual(self.state()['status'], 'waiting')
        self.assertTrue(self.state()['auto_resume'])
        self.assertEqual(self.start().wait(timeout=5), 0)
        self.assertEqual(self.state()['status'], 'done')
        self.assertEqual(self.state()['output_template'], original['output_template'])

    def test_url_validation(self):
        self.assertEqual(module.canonical_url('https://youtu.be/abc123DEF45?list=ignore')[1],URL)
        self.assertEqual(module.canonical_url('https://example.com/article#section'), ('article', 'https://example.com/article'))
        self.assertEqual(module.canonical_url('https://evil-youtube.com/watch?v=abc123DEF45')[0], 'article')
        for bad in ('--exec=bad','https://youtube.com/@channel','file:///tmp/video'):
            with self.assertRaises(ValueError):module.canonical_url(bad)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        for name, value in [('STATE', self.state)]:
            context = patch.object(module, name, value)
            context.start()
            self.addCleanup(context.stop)
        self.spawn = patch.object(module, 'detached').start()
        self.online = patch.object(module, 'reachable', return_value=True).start()
        self.addCleanup(patch.stopall)
        self.key = module.job_key(URL)

    def job(self, status='waiting', **extra):
        data = dict(key=self.key, url=URL, status=status, auto_resume=True,
                    pid=0, process_start=None, updated=0, title='Saved title')
        data.update(extra)
        (self.state/f'{self.key}.json').write_text(json.dumps(data))
        return data

    def test_offline_waits_then_reconnect_queues_once(self):
        self.job('downloading')
        self.online.return_value = False
        module.recover()
        self.spawn.assert_not_called()
        waiting = module.read_job(self.key)
        self.assertEqual(waiting['status'], 'waiting')
        module.recover()
        self.assertEqual(module.read_job(self.key)['updated'], waiting['updated'])
        self.online.return_value = True
        module.recover()
        self.assertEqual(self.spawn.call_count, 1)
        args = self.spawn.call_args.args[0]
        self.assertEqual(args[0], '--worker')
        self.assertEqual(args[2], URL)
        module.recover()
        self.assertEqual(self.spawn.call_count, 1)

    def test_playlist_queue_is_persistent_deduplicated_and_bounded(self):
        urls=[f'https://www.youtube.com/watch?v=abc123DEF4{i}' for i in range(5)]
        for url in urls:module.enqueue(url,'Episode',batch='playlist',defer=True)
        self.spawn.assert_not_called()
        first=module.read_job(module.job_key(urls[0]))
        self.assertEqual(module.detail(first),'Queued')
        module.enqueue(urls[0],'Episode',batch='playlist',defer=True)
        self.assertEqual(module.read_job(first['key'])['worker_token'],first['worker_token'])
        module.recover()
        self.assertEqual(self.spawn.call_count,3)
        module.recover()
        self.assertEqual(self.spawn.call_count,3)
        started=self.spawn.call_args_list[0].args[0][2]
        key=module.job_key(started);job=module.read_job(key)
        job['status']='done';module.save(job)
        module.recover()
        self.assertEqual(self.spawn.call_count,4)
        self.assertEqual(len(list(self.state.glob('*.json'))),5)

    def test_playlist_worker_cannot_exceed_three_download_slots(self):
        import fcntl
        from contextlib import ExitStack
        self.job(batch='playlist',worker_token='current')
        with ExitStack() as stack:
            for number in range(3):
                slot=stack.enter_context((self.state/f'.playlist-slot-{number}.lock').open('a'))
                fcntl.flock(slot,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(module.download(URL,worker_token='current'),0)
            self.assertEqual(module.read_job(self.key)['status'],'waiting')

    def test_completed_workers_do_not_occupy_playlist_slots(self):
        for i in range(3):
            url=f'https://www.youtube.com/watch?v=abc123DEF4{i}'
            key=module.job_key(url)
            module.save(dict(key=key,url=url,status='done',batch='playlist',auto_resume=True,
                             pid=os.getpid(),process_start=module.process_start(os.getpid())))
        module.enqueue(URL,'Next episode',batch='playlist',defer=True)
        module.recover()
        self.assertEqual(self.spawn.call_count,1)

    def test_zombie_worker_is_not_alive(self):
        pid=os.fork()
        if pid==0:os._exit(0)
        try:
            os.waitid(os.P_PID,pid,os.WEXITED|os.WNOWAIT)
            self.assertIsNone(module.process_start(pid))
        finally:os.waitpid(pid,0)

    def test_reopening_retries_failed_but_excludes_finished_deleted_cancelled_legacy(self):
        for status in ('done', 'deleted', 'cancelled'):
            self.job(status)
            module.recover(reopened=True)
        self.job('failed', auto_resume=False)
        module.recover(reopened=True)
        self.spawn.assert_not_called()
        self.job('failed')
        module.recover()
        self.spawn.assert_not_called()
        module.recover(reopened=True)
        self.spawn.assert_called_once()

    def test_waiting_waybar_never_looks_complete(self):
        view = module.waybar([self.job()])
        self.assertEqual(view['text'], '…')
        self.assertEqual(view['class'], 'downloading')
        self.assertIn('Waiting to resume', view['tooltip'])

    def test_orphan_downloader_is_not_duplicated(self):
        self.job('downloading', child_pid=os.getpid(), child_start=module.process_start(os.getpid()))
        module.recover(reopened=True)
        self.spawn.assert_not_called()

    def test_cancel_waiting_invalidates_queued_worker(self):
        self.job(worker_token='old')
        self.assertEqual(module.cancel_job(self.key), 0)
        self.assertEqual(module.download(URL, worker_token='old'), 0)
        module.recover(reopened=True)
        self.spawn.assert_not_called()
        self.assertEqual(module.read_job(self.key)['status'], 'cancelled')

    def test_stale_worker_cannot_restart_deleted_job(self):
        self.job('deleted', worker_token='old')
        self.assertEqual(module.download(URL, worker_token='old'), 0)
        self.assertEqual(module.read_job(self.key)['status'], 'deleted')


if __name__=='__main__':unittest.main()
