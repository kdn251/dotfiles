#!/usr/bin/env python3
"""Check YouTube's stream listings without extracting media or downloading."""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from stream_profile import cache_avatar
from stream_live_cache import OfflineError, update_live_list, menu


def resolve(data):
    if not isinstance(data.get('entries'), list):
        raise ValueError('YouTube did not return a stream listing.')
    for entry in data['entries']:
        if not entry or entry.get('live_status') != 'is_live':
            continue
        video_id = entry.get('id', '')
        if re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
            return {'url': f'https://www.youtube.com/watch?v={video_id}',
                    'title': entry.get('title') or 'YouTube live stream'}
    raise OfflineError('This channel is offline on YouTube. Try again when the stream is live.')


def fetch(channel):
    if not re.fullmatch(r'https://(?:www\.)?youtube\.com/(?:@[\w.-]+|channel/[\w-]+)/?', channel):
        raise ValueError('Expected a YouTube @handle or channel URL.')
    downloader = Path.home() / '.local/bin/yt-dlp'
    executable = str(downloader) if downloader.is_file() else shutil.which('yt-dlp')
    if not executable:
        raise ValueError('yt-dlp is not installed.')
    result = subprocess.run(
        [executable, '--ignore-config', '--flat-playlist', '--playlist-end', '15',
         '--dump-single-json', '--socket-timeout', '10', '--retries', '1',
         channel.rstrip('/') + '/streams'],
        capture_output=True, text=True, timeout=40)
    if result.returncode:
        raise ValueError('Unable to check YouTube live status; try again shortly.')
    data = json.loads(result.stdout)
    avatar = next((t['url'] for t in data.get('thumbnails', [])
                   if t.get('id') == 'avatar_uncropped'), '')
    icon = cache_avatar(channel, avatar)
    return dict(resolve(data), icon=icon)


def main():
    cache = Path.home() / '.cache/youtube-live.json'
    if sys.argv[1:] == ['--update']:
        update_live_list(Path.home() / 'scripts/youtube_live_channels.tsv', cache, fetch)
    elif sys.argv[1:] == ['--menu']:
        menu(cache, 'YouTube')
    else:
        print(json.dumps(fetch(sys.argv[1])))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
