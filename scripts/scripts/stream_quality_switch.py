#!/usr/bin/env python3
"""Replace live video quality without unloading the playing audio track."""
import json
import sys
from mpv_clip import Player


def switch(endpoint, target, label):
    player=Player(str(endpoint))
    try:
        session=player.get('user-data/stream-ready-session')
        original=player.get('path')
        if not session:
            raise ValueError('Wait for the live stream to start before changing quality.')
        if player.get('rebase-start-time', True):
            raise ValueError('Reopen the stream once to enable audio-preserving quality changes.')
        tracks=player.get('track-list', [])
        old_ids={(t['type'],t['id']) for t in tracks}
        old_video=player.get('vid')
        player.command('show-text','Preparing '+label+' video…',3000)
        # External-track loading runs in MPV's worker thread. The current
        # audio and video continue until this demuxer is ready for selection.
        player.command('video-add',target,'auto','Stream quality: '+label)
        if session!=player.get('user-data/stream-ready-session') or original!=player.get('path'):
            raise ValueError('Stream changed while preparing quality; ignored the old request.')
        added=[t for t in player.get('track-list',[]) if (t['type'],t['id']) not in old_ids]
        videos=[t for t in added if t['type']=='video' and t.get('external')]
        if not videos:
            raise ValueError('No replacement video track was available; kept the current quality.')
        video=videos[0]
        try:
            player.command('set_property','vid',video['id'])
        except ValueError:
            player.command('set_property','vid',old_video)
            raise
        # Do not retain redundant audio or old external quality demuxers.
        for track in added:
            if track['type']=='audio':player.command('audio-remove',track['id'])
        for track in tracks:
            if track['type']=='video' and track.get('external') and str(track.get('title','')).startswith('Stream quality: '):
                player.command('video-remove',track['id'])
        player.command('show-text','Quality: '+label,2500)
    finally:
        player.close()


if __name__=='__main__':
    try:switch(*sys.argv[1:4])
    except (OSError,ValueError) as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
