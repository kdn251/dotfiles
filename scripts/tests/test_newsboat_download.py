"""Offline downloader lifecycle, notification, and Waybar regression checks."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

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
for amount in (10,60,100):
 print('NBPROGRESS:'+json.dumps(dict(downloaded_bytes=amount,total_bytes=100)),flush=True)
 time.sleep(float(os.environ.get('DELAY','0.03')))
if mode=='download':
 print('HTTP 403: deliberate download failure',file=sys.stderr);sys.exit(1)
if mode!='missing':
 target=folder/'video [abc123DEF45].mp4';target.write_bytes(b'finished-video')
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

    def test_url_validation(self):
        self.assertEqual(module.canonical_url('https://youtu.be/abc123DEF45?list=ignore')[1],URL)
        self.assertEqual(module.canonical_url('https://example.com/article#section'), ('article', 'https://example.com/article'))
        self.assertEqual(module.canonical_url('https://evil-youtube.com/watch?v=abc123DEF45')[0], 'article')
        for bad in ('--exec=bad','https://youtube.com/@channel','file:///tmp/video'):
            with self.assertRaises(ValueError):module.canonical_url(bad)


if __name__=='__main__':unittest.main()
