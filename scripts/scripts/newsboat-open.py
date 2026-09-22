#!/usr/bin/env python3
"""o/O: play YouTube videos; open other links in Brave."""
import os
from pathlib import Path
import sys
from newsboat_media import identity


def launcher_for(url):
    video = identity(url)
    return 'newsboat-play-video.sh' if video and video[0] == 'youtube' else 'newsboat-brave-app.sh'


if __name__ == '__main__':
    url = sys.argv[1]
    launcher = Path(__file__).resolve().with_name(launcher_for(url))
    os.execv(str(launcher), [str(launcher), url])
