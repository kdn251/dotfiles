#!/usr/bin/env python3
"""Newsboat video downloads and the existing Twitch VOD Waybar module."""
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import parse_qs, urlparse
from newsboat_media import rebuild

SCRIPTS = Path(__file__).resolve().parent
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'newsboat/downloads'
VIDEOS = Path(os.environ.get('NEWSBOAT_VIDEO_DIR', Path.home() / 'Videos/newsboat'))
ACTIVE = {'preparing', 'downloading', 'processing'}
FINISHED_SECONDS = 5
FAILED_SECONDS = 5
FORMAT = 'bestvideo[height<=?1440]+bestaudio/best[height<=?1440]/best'


def canonical_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme not in {'http', 'https'}:
        raise ValueError('Expected a YouTube or Twitch video URL')
    if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}:
        parts = parsed.path.strip('/').split('/')
        video = parts[0] if host == 'youtu.be' else parse_qs(parsed.query).get('v', [''])[0]
        if not video and parts[0] in {'shorts', 'live', 'embed'} and len(parts) > 1:
            video = parts[1]
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video):
            raise ValueError('Expected a single YouTube video, not a channel or playlist')
        return 'youtube', f'https://www.youtube.com/watch?v={video}'
    if host in {'twitch.tv', 'www.twitch.tv', 'm.twitch.tv', 'clips.twitch.tv'} and parsed.path.strip('/'):
        return 'twitch', f'https://{host.removeprefix("www.").removeprefix("m.")}{parsed.path.rstrip("/")}'
    raise ValueError('Only YouTube and Twitch URLs are supported')


def job_key(url):
    return hashlib.sha256(url.encode()).hexdigest()[:24]


def process_start(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def alive(job):
    return bool(job.get('process_start')) and process_start(job.get('pid', 0)) == job['process_start']


def save(job):
    job['updated'] = time.time()
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = STATE / f'{job["key"]}.json'
    tmp = target.with_suffix('.tmp')
    tmp.write_text(json.dumps(job))
    tmp.chmod(0o600)
    tmp.replace(target)
    from newsboat_download_status import publish
    publish(STATE)


def notify(job, phase):
    if phase == 'Download failed':
        # Waiting for a notification action must not hold the download lock
        # or keep Waybar in an active state after the worker has finished.
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()),
                          '--failure-notification', job['key']],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return
    # Critical popups never expire in this desktop's SwayNC configuration.
    # Use normal urgency for all download results and keep the real daemon ID
    # so completion/failure replaces the starting popup instead of stacking.
    args = ['notify-send', '-a', phase, '-p', '-r', str(job.get('notification_id', 0)),
            '-t', '5000', '-u', 'normal']
    if job.get('icon'):
        args += ['-i', job['icon']]
    # Keep the result visible even when the daemon hides the application label.
    title = f'{phase}: {job["title"]}'
    args += ['--', title]
    try:
        result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                text=True, timeout=3)
        if result.returncode == 0 and result.stdout.strip().isdigit():
            job['notification_id'] = int(result.stdout.strip())
            save(job)
    except (OSError, subprocess.TimeoutExpired):
        pass  # A notification outage must never fail the download.


def failure_notification(key):
    if not re.fullmatch(r'[0-9a-f]{24}', key):
        return 1
    job = json.loads((STATE / f'{key}.json').read_text())
    if job['status'] != 'failed':
        return 0
    args = ['notify-send', '-a', 'Download failed', '-p', '-r', str(job.get('notification_id', 0)),
            '-t', '5000', '-u', 'normal', '--wait', '-A', 'retry=Retry']
    if job.get('icon'):
        args += ['-i', job['icon']]
    args += ['--', f'Download failed: {job["title"]}']
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=12)
        if 'retry' in result.stdout.splitlines():
            subprocess.Popen([sys.executable, str(Path(__file__).resolve()), job['url']],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 0


def creator_icon(platform, info):
    identity = info.get('channel_id') if platform == 'youtube' else info.get('uploader_id')
    if not identity:
        return ''
    helper = 'yt-channel-pic.sh' if platform == 'youtube' else 'twitch-profile-pic.sh'
    try:
        result = subprocess.run([str(SCRIPTS / helper), identity], capture_output=True,
                                text=True, timeout=25)
        image = Path(result.stdout.strip())
        return str(image) if result.returncode == 0 and image.is_file() else ''
    except (OSError, subprocess.TimeoutExpired):
        return ''


def stop(process):
    if process is not None and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        except ProcessLookupError:
            pass


class Cancelled(Exception):
    pass


def cookie_retry_options(platform, diagnostics):
    if platform != 'youtube' or 'not a bot' not in diagnostics.lower():
        return []
    # Hyprland's automatic keyring detection chooses basic, but Brave uses
    # GNOME Keyring here. Read the browser session in memory; never export it.
    browser = os.environ.get('NEWSBOAT_YOUTUBE_BROWSER', 'brave+gnomekeyring')
    return ['--cookies-from-browser', browser]


def download(url, title=''):
    platform, url = canonical_url(url)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    key = job_key(url)
    lock = (STATE / f'{key}.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return 0
    job = dict(key=key, url=url, platform=platform, title=title or 'Fetching video details',
               creator='', icon='', status='preparing', bytes=0, percent=None,
               pid=os.getpid(), process_start=process_start(os.getpid()),
               log=str(STATE / f'{key}.log'))
    process = None
    previous_handlers = {}

    def cancel(*_):
        raise Cancelled()

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        previous_handlers[sig] = signal.signal(sig, cancel)
    save(job)
    # Match the working mpv launcher even when Newsboat has the desktop PATH.
    env = dict(os.environ, PATH=f'{Path.home()}/.local/bin:{os.environ.get("PATH", "")}')
    ytdlp = str(Path.home() / '.local/bin/yt-dlp')
    if not os.access(ytdlp, os.X_OK):
        ytdlp = 'yt-dlp'
    try:
        with tempfile.TemporaryDirectory(prefix='newsboat-video-') as temp, open(job['log'], 'w') as log:
            os.chmod(job['log'], 0o600)
            process = subprocess.Popen([ytdlp, '--no-playlist', '--dump-single-json', '-f', FORMAT,
                                        '--', url], stdout=subprocess.PIPE, stderr=log,
                                       env=env, start_new_session=True)
            raw, _ = process.communicate()
            session_options = []
            if process.returncode:
                log.flush()
                session_options = cookie_retry_options(platform, Path(job['log']).read_text(errors='replace'))
                if session_options:
                    log.write('Retrying YouTube with the existing Brave session.\n')
                    log.flush()
                    process = subprocess.Popen([ytdlp, *session_options, '--no-playlist',
                                                '--dump-single-json', '-f', FORMAT, '--', url],
                                               stdout=subprocess.PIPE, stderr=log, env=env,
                                               start_new_session=True)
                    raw, _ = process.communicate()
            if process.returncode:
                raise RuntimeError('YouTube sign-in retry failed; open the video in Brave and try again'
                                   if session_options else 'Could not fetch video details; see the download log')
            info = json.loads(raw)
            if not isinstance(info, dict) or not info.get('id'):
                raise RuntimeError('The URL did not resolve to a video')
            job.update(title=info.get('title') or title or 'Video',
                       creator=info.get('channel') or info.get('uploader') or platform,
                       video_id=str(info['id']), icon=creator_icon(platform, info))
            # Keep manually requested Twitch videos outside the cron pruner's
            # top-level VOD directory, so it cannot remove an active download.
            folder = VIDEOS / ('downloaded-videos' if platform == 'youtube' else 'twitch-vods/manual')
            folder.mkdir(parents=True, exist_ok=True)
            metadata = Path(temp) / 'video.json'
            metadata.write_bytes(raw)
            outputs = Path(temp) / 'finished.jsonl'
            job.update(status='downloading', folder=str(folder))
            save(job)
            notify(job, 'Downloading')
            command = [ytdlp, *session_options, '--no-playlist', '--load-info-json', str(metadata),
                       '--no-simulate', '-f', FORMAT, '--merge-output-format', 'mp4',
                       '--restrict-filenames', '--no-overwrites', '--newline', '--progress',
                       '--progress-delta', '1',
                       '--progress-template', 'download:NBPROGRESS:%(progress)j',
                       '--progress-template', 'postprocess:NBPOST:%(progress.status)s',
                       '--print-to-file', 'after_move:%(filepath)j', str(outputs),
                       '-o', str(folder / '%(title).180B [%(id)s].%(ext)s')]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log,
                                       env=env, text=True, start_new_session=True)
            for line in process.stdout:
                if line.startswith('NBPROGRESS:'):
                    progress = json.loads(line.removeprefix('NBPROGRESS:'))
                    size = progress.get('total_bytes') or progress.get('total_bytes_estimate')
                    received = progress.get('downloaded_bytes') or 0
                    job.update(bytes=received, percent=min(100, 100 * received / size) if size else None)
                    save(job)
                elif line.startswith('NBPOST:'):
                    job.update(status='processing', percent=None)
                    save(job)
                else:
                    log.write(line)
            process.stdout.close()
            if process.wait():
                raise RuntimeError('The video download failed; see the download log')
            paths = [Path(json.loads(line)) for line in outputs.read_text().splitlines()] if outputs.exists() else []
            if not paths or not all(p.is_file() and p.stat().st_size > 0 for p in paths):
                raise RuntimeError('Downloader exited without a finished video file')
            job.update(status='done', percent=100, bytes=sum(p.stat().st_size for p in paths),
                       files=[str(p) for p in paths])
            save(job)
            notify(job, 'Download complete')
            try:
                rebuild()
            except (OSError, ValueError) as error:
                # A library-update failure does not turn a saved video into
                # a failed download. Preserve diagnostics for a manual retry.
                log.write(f'Library update failed: {error}\n')
            return 0
    except Cancelled:
        stop(process)
        job.update(status='cancelled', percent=None)
        save(job)
        notify(job, 'Download cancelled')
        # Partial files are deliberately retained so another ,d can resume.
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        stop(process)
        job.update(status='failed', error=str(error), percent=None)
        save(job)
        notify(job, 'Download failed')
        return 1
    finally:
        stop(process)
        if process is not None and process.stdout is not None:
            process.stdout.close()
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
        lock.close()


def legacy_downloads():
    """Keep the scheduled Streamlink VOD downloads in the existing module."""
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().decode(errors='replace').split('\0')
            if not any(Path(arg).name == 'streamlink' for arg in args[:3]) or '--output' not in args:
                continue
            path = Path(args[args.index('--output') + 1])
            creator, _, rest = path.stem.partition(' - ')
            title = rest.rsplit(' - ', 1)[0] or path.stem
            icon = Path.home() / '.cache/twitch-profiles' / f'{creator.lower()}.png'
            yield dict(key=f'legacy-{proc.name}', pid=int(proc.name), process_start=process_start(proc.name),
                       creator=creator, title=title, status='downloading', percent=None,
                       bytes=path.stat().st_size if path.exists() else 0,
                       icon=str(icon) if icon.is_file() else '', files=[str(path)])
        except (OSError, IndexError):
            continue


def jobs():
    found = []
    for path in STATE.glob('*.json'):
        try:
            job = json.loads(path.read_text())
            if job.get('status') == 'deleted':
                continue
            if job['status'] in ACTIVE and not alive(job):
                job.update(status='failed', error='Download process stopped unexpectedly')
                save(job)
            ttl = FAILED_SECONDS if job['status'] == 'failed' else FINISHED_SECONDS
            if job['status'] in ACTIVE or time.time() - job['updated'] < ttl:
                found.append(job)
        except (OSError, ValueError, KeyError):
            continue
    return sorted(found, key=lambda j: (j['status'] not in ACTIVE, -j['updated'])) + list(legacy_downloads())


def size_text(value):
    return f'{value / 1024**3:.1f} GB' if value >= 1024**3 else f'{value / 1024**2:.1f} MB'


def detail(job):
    labels = {'preparing': 'Preparing', 'downloading': 'Downloading', 'processing': 'Merging',
              'done': 'Complete', 'failed': 'Failed', 'cancelled': 'Cancelled'}
    text = labels[job['status']]
    if job.get('percent') is not None and job['status'] == 'downloading':
        text += f' {job["percent"]:.0f}%'
    if job.get('bytes'):
        text += f' · {size_text(job["bytes"])}'
    return text


def waybar(items):
    if not items:
        return {'text': ''}
    active = sum(j['status'] in ACTIVE for j in items)
    failed = any(j['status'] == 'failed' for j in items)
    icon = '\U000f01da' if active else ('✕' if failed else '✓')
    text = f'{icon} {active}' if active > 1 else icon
    tooltip = '\n\n'.join(html.escape(f'{j["title"]}\n'
                          + (f'{j["creator"]} · ' if j.get('creator') else '')
                          + detail(j)) for j in items)
    return dict(text=text, tooltip=tooltip, **{'class': 'downloading' if active else ('failed' if failed else 'done')})


def cancel_job(key):
    match = next((j for j in jobs() if j['key'] == key and j['status'] in ACTIVE), None)
    if not match or not alive(match):
        return 1
    # Check both process start time and command before signaling. Completed
    # jobs can remain in the panel after their original PID has been reused.
    args = Path(f'/proc/{match["pid"]}/cmdline').read_bytes().split(b'\0')
    expected = b'streamlink' if key.startswith('legacy-') else b'newsboat-download.py'
    if not any(Path(os.fsdecode(arg)).name == expected.decode() for arg in args[:3]):
        return 1
    os.kill(match['pid'], signal.SIGTERM)
    return 0


def panel():
    items = jobs()
    if not items:
        subprocess.run(['notify-send', '-a', 'Downloads', '-t', '3000', 'No recent downloads'])
        return 0
    body = '\n\n'.join(f'<b>{html.escape(j["title"])}</b>\n{html.escape(detail(j))}' for j in items)
    args = ['notify-send', '-a', 'Downloads', '-u', 'low', '-t', '20000', '--wait']
    icon = next((j['icon'] for j in items if j.get('icon')), '')
    if icon:
        args += ['-i', icon]
    actions = {}
    for i, job in enumerate(items):
        if job['status'] in ACTIVE:
            action = f'cancel{i}'
            args += ['-A', f'{action}=Cancel {job["title"][:24]}']
            actions[action] = job['key']
    args += ['Downloads', body]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, text=True)
    pidfile = Path(os.environ.get('XDG_RUNTIME_DIR', '/tmp')) / 'waybar-panel-twitchdl.pid'
    pidfile.write_text(str(process.pid))
    try:
        choice, _ = process.communicate()
    finally:
        pidfile.unlink(missing_ok=True)
    return cancel_job(actions[choice.strip()]) if choice.strip() in actions else 0


def main(args):
    os.umask(0o077)
    if args == ['--waybar']:
        print(json.dumps(waybar(jobs())))
        return 0
    if args == ['--list']:
        print(json.dumps(jobs()))
        return 0
    if args == ['--panel']:
        return panel()
    if len(args) == 2 and args[0] == '--failure-notification':
        return failure_notification(args[1])
    if len(args) == 2 and args[0] == '--cancel':
        return cancel_job(args[1])
    if len(args) == 2 and args[0] == '--cancel-url':
        return cancel_job(job_key(canonical_url(args[1])[1]))
    if args and not args[0].startswith('-'):
        return download(args[0], ' '.join(args[1:]))
    print('Usage: newsboat-download-video.sh VIDEO_URL [TITLE]', file=sys.stderr)
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    except (ValueError, OSError) as error:
        print(f'Newsboat download: {error}', file=sys.stderr)
        sys.exit(1)
