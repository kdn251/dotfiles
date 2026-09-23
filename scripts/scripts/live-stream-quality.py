#!/usr/bin/env python3
"""Quality cycling for the launcher's YouTube and Rumble live players."""
import fcntl
import json
import re
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen


def ipc(path, command):
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(5)
        connection.connect(str(path))
        connection.sendall((json.dumps({'command': command, 'request_id': 71}) + '\n').encode())
        with connection.makefile('rb') as stream:
            for line in stream:
                reply = json.loads(line)
                if reply.get('request_id') == 71:
                    if reply.get('error') != 'success':
                        raise ValueError(reply.get('error'))
                    return reply.get('data')
    raise ValueError('Player disconnected')


def variants(manifest, base):
    result = {}
    pending = None
    for line in manifest.splitlines():
        line = line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'):
            height = re.search(r'RESOLUTION=\d+x(\d+)', line)
            bandwidth = re.search(r'(?:[:,])BANDWIDTH=(\d+)', line)
            pending = (int(height[1]), int(bandwidth[1]) if bandwidth else 0) if height else None
        elif line and not line.startswith('#') and pending:
            height, bandwidth = pending
            if height not in result or bandwidth > result[height][0]:
                result[height] = (bandwidth, urljoin(base, line))
            pending = None
    return {height: pair[1] for height, pair in result.items()}


def next_quality(current, available):
    return available[(available.index(current) + 1) % len(available)] if current in available else available[0]


def cycle(service, path, context_path):
    context = json.loads(context_path.read_text())
    url = context['url']
    options = {}
    if service == 'youtube':
        quality = next_quality(context.get('quality', 'best'), ['best', '720p', '480p', '360p'])
        height = {'best': 1080, '720p': 720, '480p': 480, '360p': 360}[quality]
        options['ytdl-format'] = f'bestvideo[height<={height}]+bestaudio/best[height<={height}]'
        target = url
    else:
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://rumble.com/'}), timeout=15) as response:
            choices = variants(response.read(2 * 1024 * 1024).decode(), response.url)
        if not choices:
            raise ValueError('This stream does not offer switchable quality levels.')
        heights = sorted(choices, reverse=True)
        labels = ['best'] + [f'{h}p' for h in heights[1:]]
        quality = next_quality(context.get('quality', 'best'), labels)
        target = choices[heights[labels.index(quality)]]
    # Stay at the live edge; never reuse an absolute DVR timestamp as a seek.
    paused = ipc(path, ['get_property', 'pause'])
    options['pause'] = 'yes' if paused else 'no'
    ipc(path, ['loadfile', target, 'replace', 0, options])
    context['quality'] = quality
    context_path.write_text(json.dumps(context))
    ipc(path, ['show-text', f'Quality: {quality}', 2500])
    args = ['notify-send', '-a', 'Quality', '-t', '2500']
    if context.get('icon'):
        args += ['-i', context['icon']]
    subprocess.run(args + [context.get('title', service.title()), f'Switching quality: {quality}'], check=False)


def main():
    for service in ('youtube', 'rumble'):
        path = Path(f'/tmp/mpv-{service}-live-ipc')
        try:
            ipc(path, ['get_property', 'path'])
        except (OSError, ValueError):
            continue
        context = Path.home() / f'.cache/{service}-live-player.json'
        with (Path.home() / f'.cache/{service}-live-quality.lock').open('w') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return 0
            try:
                cycle(service, path, context)
            except Exception as error:
                subprocess.run(['notify-send', '-a', 'Quality', '-t', '5000',
                                'Quality change failed', str(error)], check=False)
                return 1
        return 0
    return 2  # Let the existing Twitch/YouTube-video handler run.


if __name__ == '__main__':
    sys.exit(main())
