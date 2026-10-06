#!/usr/bin/env python3
"""Resolve a video for replacement inside the existing mpv window."""
import json
import os
import sys
import newsboat_media as media
import newsboat_autoplay as autoplay


def target(url,title='',queue=False):
    os.environ['NEWSBOAT_QUEUE_PLAYBACK']='1' if queue else '0'
    local=media.playback_file(url)
    return dict(url=url,path=str(local) if local else url,title=title or media.cached_title(url),
                local=bool(local),plan=autoplay.plan(url))


if __name__=='__main__':
    print(json.dumps(target(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else '',len(sys.argv)>3 and sys.argv[3]=='queue')))
