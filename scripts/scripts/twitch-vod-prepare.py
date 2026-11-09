#!/usr/bin/env python3
"""Finalize fragmented VODs without re-encoding or exposing partial replacements."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import struct
import subprocess
import sys
import time

SCRIPTS = Path(__file__).resolve().parent


def fragmented(path):
    with Path(path).open('rb') as stream:
        if stream.read(8)[4:] != b'ftyp':
            return False
        stream.seek(0)
        end = os.fstat(stream.fileno()).st_size
        while stream.tell() < end:
            start = stream.tell()
            header = stream.read(8)
            if len(header) != 8:
                raise ValueError('Truncated MP4 header')
            size, kind = struct.unpack('>I4s', header)
            if size == 1:
                size = struct.unpack('>Q', stream.read(8))[0]
            if size == 0:
                size = end - start
            if size < 8 or start + size > end:
                raise ValueError('Invalid MP4 box size')
            if kind == b'moof':
                return True
            stream.seek(start + size)
    return False


def playing(path):
    target = Path(path).resolve()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if proc.joinpath('comm').read_text().strip() != 'mpv':
                continue
            for fd in proc.joinpath('fd').iterdir():
                try:
                    if fd.resolve() == target:
                        return True
                except OSError:
                    pass
        except OSError:
            pass
    return False


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
        'stream=codec_type,codec_name:format=duration,start_time', '-of', 'json', str(path)],
        capture_output=True, text=True, check=True, timeout=120)
    info = json.loads(result.stdout)
    codecs = sorted((s['codec_type'], s['codec_name']) for s in info['streams']
                    if s['codec_type'] in ('audio', 'video'))
    if not codecs or not any(kind == 'video' for kind, _ in codecs):
        raise ValueError('No video stream')
    # Fragmented input duration includes its nonzero starting timestamp.
    duration = float(info['format']['duration']) - float(info['format'].get('start_time', 0))
    return codecs, duration


def remux(path, temp):
    command = [sys.executable, str(SCRIPTS/'newsboat-ffmpeg/ffmpeg'),
        '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(path),
        '-map', '0:v', '-map', '0:a?', '-c', 'copy', str(temp)]
    child = subprocess.Popen(command, env=dict(os.environ, NEWSBOAT_FFMPEG_BYTE_PACING='1'))
    try:
        status = child.wait()
        if status:
            raise subprocess.CalledProcessError(status, command)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def prepare(path):
    path = Path(path).resolve()
    lock = Path(str(path) + '.prepare.lock').open('a')
    with lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not fragmented(path):
            return False
        if playing(path):
            raise RuntimeError('VOD is playing; preparation deferred until next run')
        original = path.stat()
        temp = path.with_name('.' + path.name + '.preparing.mp4')
        temp.unlink(missing_ok=True)  # stale output from an interrupted attempt
        if shutil.disk_usage(path.parent).free < original.st_size * 1.1 + 1024**3:
            raise RuntimeError('Not enough free space for a verified replacement')
        before = probe(path)
        print('Preparing:', path.name, flush=True)
        try:
            remux(path, temp)
            after = probe(temp)
            if before[0] != after[0] or abs(before[1] - after[1]) > max(2, before[1] * .001):
                raise ValueError(f'Replacement validation failed: {before} versus {after}')
            if fragmented(temp):
                raise ValueError('Replacement is still fragmented')
            now = path.stat()
            if (now.st_size, now.st_mtime_ns) != (original.st_size, original.st_mtime_ns) or playing(path):
                raise RuntimeError('Original changed or began playing; leaving it intact')
            os.chmod(temp, original.st_mode & 0o777)
            os.utime(temp, ns=(original.st_atime_ns, original.st_mtime_ns))
            with temp.open('rb') as stream:
                os.fsync(stream.fileno())
            os.replace(temp, path)
            # Update the fast playback index without rebuilding unrelated downloads.
            import newsboat_media as media
            with media.library_lock():
                index_path = media.STATE/'.media-index.json'
                try:
                    index = json.loads(index_path.read_text())
                except (OSError, ValueError):
                    index = {}
                entry = index.setdefault(str(path), {})
                stat = path.stat()
                entry.update(signature=[stat.st_size, stat.st_mtime_ns], valid=True,
                             checked_at=time.time())
                entry.setdefault('downloaded_at', original.st_mtime)
                media.atomic_write(index_path, json.dumps(index))
            print('Prepared:', path.name, flush=True)
            return True
        finally:
            temp.unlink(missing_ok=True)


def main():
    def interrupted(signum, frame):
        raise InterruptedError('VOD preparation interrupted; original retained')
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    parser = argparse.ArgumentParser()
    parser.add_argument('path', nargs='?')
    parser.add_argument('--repair-all', action='store_true')
    args = parser.parse_args()
    import newsboat_media as media
    paths = sorted((media.ROOT/'twitch-vods').glob('*.mp4')) if args.repair_all else [Path(args.path)]
    failed = False
    for path in paths:
        if path.name.startswith('.') or (args.repair_all and any(Path(str(path)+s).exists()
                for s in ('.incomplete', '.part', '.ytdl'))):
            continue
        try:
            prepare(path)
        except InterruptedError:
            raise
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            print(f'{path.name}: {error}', file=sys.stderr, flush=True)
            failed = True
    subprocess.run([sys.executable, str(SCRIPTS/'newsboat-vods.py'), 'rebuild'],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
