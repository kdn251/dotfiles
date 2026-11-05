#!/usr/bin/env python3
"""Check YouTube's stream listings without extracting media or downloading."""
import json
import re
import shutil
import subprocess
import sys
import time
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
                    'title': entry.get('title') or 'YouTube live stream',
                    'chat_url': f'https://www.youtube.com/live_chat?v={video_id}&is_popout=1'}
    raise OfflineError('This channel is offline on YouTube. Try again when the stream is live.')


def playback_manifest(details):
    # Keep one video and one audio rendition. Opening the master makes FFmpeg
    # probe every quality, while choosing only video would silently lose audio.
    formats=[f for f in details.get('formats',[]) if f.get('protocol') in ('m3u8','m3u8_native')
             and str(f.get('url','')).startswith('https://')]
    videos=[f for f in formats if f.get('height') and f['height']<=1080]
    if not videos:return None
    video=max(videos,key=lambda f:(f['height'],f.get('fps') or 0))
    if video.get('acodec') not in ('none',None):return video['url']
    audio=[f for f in formats if f.get('vcodec')=='none']
    if not audio:return None
    sound=max(audio,key=lambda f:(f.get('language_preference') or 0,f.get('quality') or 0,
                                f.get('abr') or f.get('tbr') or 0,f.get('source_preference') or 0))
    return 'edl://'+';'.join('!new_stream;!no_clip;%'+str(len(f['url'].encode()))+'%'+f['url'] for f in (video,sound))


def recent_stream(channel,now=None):
    try:
        values=json.loads((Path.home()/'.cache/youtube-live.json').read_text()).values()
        now=time.time() if now is None else now
        for stream in values:
            if stream.get('channel','').rstrip('/')==channel.rstrip('/') and 0<=now-stream.get('checked_at',0)<300:
                if str(stream.get('playback_url','')).startswith(('edl://','https://')):
                    return stream
    except (OSError,ValueError,TypeError):pass
    return None


def fetch(channel, enrich=True):
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
    stream=dict(resolve(data), icon=icon)
    if enrich:
        try:
            result=subprocess.run([executable,'--ignore-config','--skip-download','--dump-single-json',
                '--no-playlist','--socket-timeout','8','--retries','0',stream['url']],
                capture_output=True,text=True,timeout=25)
            details=json.loads(result.stdout) if result.returncode==0 else {}
            manifest=playback_manifest(details)
            if manifest:stream['playback_url']=manifest
            stream['started_at'] = details.get('release_timestamp')
            viewers=details.get('concurrent_view_count')
            if isinstance(viewers,(int,float)):stream['viewer_count']=viewers
            category=details.get('game') or next(iter(details.get('categories') or []),None)
            if isinstance(category,str):stream['category']=category
        except (OSError,ValueError,subprocess.TimeoutExpired):pass
    return stream


def main():
    cache = Path.home() / '.cache/youtube-live.json'
    if sys.argv[1:] == ['--update']:
        update_live_list(Path.home() / 'scripts/youtube_live_channels.tsv', cache, fetch)
    elif sys.argv[1:] == ['--menu']:
        menu(cache, 'YouTube')
    else:
        print(json.dumps(recent_stream(sys.argv[1]) or fetch(sys.argv[1],enrich=True)))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
