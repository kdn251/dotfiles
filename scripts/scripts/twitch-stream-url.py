#!/usr/bin/env python3
"""Short-lived Twitch playback URLs, warmed when a picker row is highlighted."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def cached(path):
    try:
        data=json.loads(path.read_text())
        if 0 <= time.time()-data['created'] < 60 and data.get('schema') == 2 and data.get('low') and data.get('best'):
            return data
    except (OSError,ValueError,KeyError,TypeError):
        pass
    return None


def fetch(name, session=None):
    # The stock Twitch plugin probes every rendition serially. We only need
    # the master index: MPV opens/checks the selected rendition itself.
    from streamlink import Streamlink
    from streamlink.plugins.twitch import Twitch, TwitchHLSStream
    class PlaybackTwitch(Twitch):
        def _get_hls_streams(self, url, restricted_bitrates, **extra):
            return TwitchHLSStream.parse_variant_playlist(
                self.session, url, start_offset=self.time_offset,
                check_streams=False, low_latency=self.get_option('low-latency'), **extra)
    options={'disable-ads':True}
    token=Path.home()/'.newsboat/.twitch_oauth'
    if token.exists():options['api-header']=[('Authorization','OAuth '+token.read_text().strip())]
    owned=session is None
    if owned:session=Streamlink({'http-timeout':8},plugins_builtin=False)
    try:
        streams=PlaybackTwitch(session,'https://www.twitch.tv/'+name,options=options).streams()
        return {'streams':{key:{'url':stream.url} for key,stream in streams.items()}}
    finally:
        if owned:session.http.close()


def resolve(name, prefetch=False):
    if not re.fullmatch(r'[a-z0-9_]{1,25}',name):
        raise ValueError('Invalid Twitch username')
    root=Path(os.environ['XDG_RUNTIME_DIR'])/'twitch-stream-urls'
    root.mkdir(mode=0o700,exist_ok=True)
    path=root/(name+'.json')
    data=cached(path)
    if data:return data
    with (root/(name+'.lock')).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        data=cached(path)
        if data:return data
        # Limit speculative work to two channels; explicit selection bypasses
        # the budget and never waits behind an unrelated highlighted streamer.
        with (root/'prefetch.lock').open('a') as budget, (root/'prefetch-2.lock').open('a') as second:
            if prefetch:
                try:fcntl.flock(budget,fcntl.LOCK_EX|fcntl.LOCK_NB)
                except BlockingIOError:
                    try:fcntl.flock(second,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    except BlockingIOError:return None
            args=['streamlink','--twitch-disable-ads']
            token=Path.home()/'.newsboat/.twitch_oauth'
            if token.exists():args+=['--twitch-api-header','Authorization=OAuth '+token.read_text().strip()]
            try:
                from twitch_resolver import request
                payload=request(name)
                result=subprocess.CompletedProcess([], 0, json.dumps(payload))
            except (OSError, ValueError, TimeoutError):
                try:
                    result=subprocess.run([sys.executable,__file__,name,'--fetch'],
                                          capture_output=True,text=True,timeout=12)
                except subprocess.TimeoutExpired:
                    result=None
            if result is None or result.returncode:
                # Retain the upstream resolver if its plugin API changes.
                result=subprocess.run(args+['--json','https://www.twitch.tv/'+name],
                                      capture_output=True,text=True,timeout=12)
            if result.returncode:raise ValueError('Could not resolve Twitch stream')
            streams=json.loads(result.stdout)['streams']
            quality=next((key for prefix in ('360p','480p') for key in streams if key.startswith(prefix)), 'worst')
            data=dict(schema=2,created=time.time(),low=streams[quality]['url'],best=streams['best']['url'])
            if not all(data[k].startswith('https://') for k in ('low','best')):
                raise ValueError('Invalid stream URL')
            tmp=path.with_suffix('.tmp')
            tmp.write_text(json.dumps(data));tmp.chmod(0o600);tmp.replace(path)
            return data


if __name__=='__main__':
    try:
        if '--fetch' in sys.argv:
            print(json.dumps(fetch(sys.argv[1].lower())))
            raise SystemExit(0)
        data=resolve(sys.argv[1].lower(), '--prefetch' in sys.argv)
        if data and '--prefetch' not in sys.argv:
            if '--best' in sys.argv:
                # Validate just the upgrade, after low-quality playback starts.
                # An inaccessible HD rendition must not replace a working stream.
                from urllib.request import Request, urlopen
                with urlopen(Request(data['best'],headers={'User-Agent':'Mozilla/5.0'}),timeout=3) as response:
                    if b'#EXTM3U' not in response.read(256):raise ValueError('Invalid HD playlist')
                print(data['best'])
            else:
                print(data['low'])
    except (OSError,ValueError,KeyError,subprocess.TimeoutExpired):
        raise SystemExit(1)
