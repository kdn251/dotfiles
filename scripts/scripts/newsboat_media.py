#!/usr/bin/env python3
"""Exact video identities and finished-file inventory shared by Newsboat tools."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get('NEWSBOAT_VIDEO_DIR', Path.home() / 'Videos/newsboat'))
CACHE = Path.home() / '.cache/mpv-yt-videos'
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'newsboat/downloads'
URLS = Path(os.environ.get('NEWSBOAT_URLS_FILE', Path.home() / '.newsboat/urls'))
MEDIA = {'.mp4', '.webm', '.mkv', '.m4v', '.mov'}


def identity(url):
    p = urlparse(url)
    host = (p.hostname or '').removeprefix('www.').removeprefix('m.')
    parts = p.path.strip('/').split('/')
    if host in {'youtube.com', 'youtu.be'}:
        value = parts[0] if host == 'youtu.be' else parse_qs(p.query).get('v', [''])[0]
        if not value and parts[0] in {'shorts', 'live', 'embed'} and len(parts) > 1:
            value = parts[1]
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
            return 'youtube', value
    if host == 'twitch.tv' and len(parts) == 2 and parts[0] == 'videos' and parts[1].isdigit():
        return 'twitch', parts[1]
    if host == 'clips.twitch.tv' and len(parts) == 1 and re.fullmatch(r'[A-Za-z0-9_-]+', parts[0]):
        return 'twitch-clip', parts[0]
    if host == 'twitch.tv' and len(parts) == 3 and parts[1] == 'clip' and re.fullmatch(r'[A-Za-z0-9_-]+', parts[2]):
        return 'twitch-clip', parts[2]
    return None


def filename_identity(path):
    stem = path.stem
    bracket = re.search(r'\[([^\[\]]+)\]$', stem)
    if bracket:
        value = bracket[1]
    else:
        match = re.search(r'(?:^| - |[-_])([A-Za-z0-9_-]{11}|[0-9]{9,12})$', stem)
        if not match:
            return None
        value = match[1]
    if re.fullmatch(r'v[0-9]+', value):
        return 'twitch', value[1:]
    if value.isdigit() and ('twitch-vods' in path.parts or len(value) != 11):
        return 'twitch', value
    if re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        return 'youtube', value
    return None


def inside(path):
    return not path.is_symlink() and any(path.resolve().is_relative_to(root.resolve()) for root in (ROOT, CACHE))


def start_time(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def records():
    for path in STATE.glob('*.json'):
        try:
            value = json.loads(path.read_text())
            if value.get('url'):
                yield path, value
        except (OSError, ValueError):
            continue


def busy_paths():
    """Exclude media being written by a downloader or merger, including legacy jobs."""
    found = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            args = proc.joinpath('cmdline').read_bytes().split(b'\0')
            if not any(Path(os.fsdecode(a)).name in {'yt-dlp', 'streamlink', 'ffmpeg'} for a in args[:3]):
                continue
            for fd in proc.joinpath('fd').iterdir():
                with contextlib.suppress(OSError):
                    found.add(fd.resolve())
        except OSError:
            continue
    return found


def candidates():
    known = {}
    blocked = set()
    for _, job in records():
        key = identity(job['url'])
        if not key:
            continue
        if job.get('status') in {'preparing', 'downloading', 'processing'}:
            if job.get('process_start') and start_time(job.get('pid', 0)) == job['process_start']:
                blocked.add(key)
        elif job.get('status') in {'failed', 'cancelled'} and not job.get('files'):
            blocked.add(key)
        for value in job.get('files', []):
            known[Path(value)] = key
    busy = busy_paths()
    for root in (ROOT, CACHE):
        if not root.is_dir():
            continue
        for path in root.rglob('*'):
            if path.suffix.lower() not in MEDIA or not path.is_file() or not inside(path):
                continue
            key = known.get(path) or filename_identity(path)
            if not key or key in blocked or path.resolve() in busy:
                continue
            # A same-name partial/fragment is not a completed media file.
            if Path(str(path) + '.part').exists() or Path(str(path) + '.ytdl').exists():
                continue
            yield key, path


def playable(path):
    if not path.is_file() or not path.stat().st_size:
        return False
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'stream=codec_type:format=duration', '-of', 'json', str(path)],
                           capture_output=True, text=True, timeout=10)
        info = json.loads(r.stdout)
        return r.returncode == 0 and any(s.get('codec_type') in {'video', 'audio'} for s in info.get('streams', []))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def find(url):
    key = identity(url)
    if not key:
        return None
    # Explicit downloads take priority over the temporary streaming cache.
    matches = sorted((p for k, p in candidates() if k == key),
                     key=lambda p: (p.is_relative_to(CACHE), -p.stat().st_mtime))
    return next((p for p in matches if playable(p)), None)


@contextlib.contextmanager
def library_lock():
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / '.library.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def atomic_write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Follow the stowed file itself, never replace its symlink.
    target = path.resolve()
    mode = target.stat().st_mode & 0o777 if target.exists() else 0o600
    fd, name = tempfile.mkstemp(prefix='.' + target.name, dir=target.parent)
    try:
        with os.fdopen(fd, 'w') as output:
            output.write(text)
        os.chmod(name, mode)
        os.replace(name, target)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(name)


def rebuild_unlocked():
    index_path = STATE / '.media-index.json'
    try:
        old = json.loads(index_path.read_text())
    except (OSError, ValueError):
        old = {}
    index = {}
    keys = set()
    for key, path in candidates():
        # The Downloaded library holds explicit downloads, not the evictable cache.
        if path.is_relative_to(CACHE):
            continue
        stat = path.stat()
        signature = [stat.st_size, stat.st_mtime_ns]
        entry = old.get(str(path), {})
        valid = entry.get('valid') if entry.get('signature') == signature else playable(path)
        index[str(path)] = dict(signature=signature, valid=valid)
        if valid:
            keys.add(key)
    patterns = []
    youtube = sorted(value for platform, value in keys if platform == 'youtube')
    twitch = sorted(value for platform, value in keys if platform == 'twitch')
    clips = sorted(value for platform, value in keys if platform == 'twitch-clip')
    if youtube:
        patterns.append(r'^https?://(www[.]|m[.])?(youtube[.]com/(watch[?].*v=|shorts/|live/|embed/)|youtu[.]be/)('
                        + '|'.join(youtube) + r')([?&#/]|$)')
    if twitch:
        patterns.append(r'^https?://(www[.]|m[.])?twitch[.]tv/videos/(' + '|'.join(twitch) + r')([?&#/]|$)')
    if clips:
        patterns.append(r'^https?://(clips[.]twitch[.]tv/|(www[.])?twitch[.]tv/[^/]+/clip/)('
                        + '|'.join(clips) + r')([?&#/]|$)')
    expression = ' or '.join('link =~ ' + json.dumps(pattern) for pattern in patterns) or 'link = ""'
    query = json.dumps('query:📥 Downloads:(' + expression + ') and feedtitle !~ "Starred"', ensure_ascii=False) + ' downloaded'
    current = URLS.read_text() if URLS.exists() else ''
    rest = [line for line in current.splitlines() if not line.startswith(('"query:Downloaded:', '"query:📥 Downloaded:', '"query:📥 Downloads:'))]
    # Keep the unified unread inbox first when rebuilding the download library.
    position = next((i + 1 for i, line in enumerate(rest)
                     if line.startswith('"query:📰 New:')), 0)
    rest.insert(position, query)
    content = '\n'.join(rest) + '\n'
    if content != current:
        atomic_write(URLS, content)
    atomic_write(index_path, json.dumps(index))
    return len(keys)


def rebuild():
    with library_lock():
        return rebuild_unlocked()


def delete(url):
    key = identity(url)
    if not key:
        raise ValueError('Could not identify the selected video')
    with library_lock():
        for _, job in records():
            if identity(job['url']) == key and job.get('status') in {'preparing', 'downloading', 'processing'}:
                if job.get('process_start') and start_time(job.get('pid', 0)) == job['process_start']:
                    raise ValueError('Cancel this video download before deleting it')
        # No shell glob or substring match: every candidate has a parsed ID.
        paths = [p for k, p in candidates() if k == key]
        for path in paths:
            path.unlink()
            for suffix in ('.meta', '.info.json'):
                sidecar = path.with_suffix(suffix)
                if sidecar.is_file() and inside(sidecar):
                    sidecar.unlink()
        for state_path, job in records():
            if identity(job['url']) == key:
                job.update(status='deleted', files=[])
                atomic_write(state_path, json.dumps(job))
        archive = ROOT / '.downloaded-twitch-vods'
        if key[0] == 'twitch' and archive.exists():
            lines = [line for line in archive.read_text().splitlines() if line.rsplit(':', 1)[-1] != key[1]]
            atomic_write(archive, '\n'.join(lines) + ('\n' if lines else ''))
        rebuild_unlocked()
        return len(paths)


def main():
    command = sys.argv[1]
    if command == 'find':
        path = find(sys.argv[2])
        if path:
            print(path)
            return 0
        return 1
    if command == 'identity':
        key = identity(sys.argv[2])
        if key:
            print(key[1])
            return 0
        return 1
    if command == 'rebuild':
        rebuild()
        return 0
    if command == 'delete':
        count = delete(sys.argv[2])
        subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '3000',
                        'Download deleted' if count else 'No downloaded copy found'])
        return 0
    return 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, IndexError) as error:
        subprocess.run(['notify-send', '-a', 'Newsboat', '-t', '5000', 'Video action failed', str(error)])
        sys.exit(1)
