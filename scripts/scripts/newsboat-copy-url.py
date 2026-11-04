#!/usr/bin/env python3
"""Copy an item's original web URL to the Wayland clipboard."""
import math
import re
import subprocess
import sys
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse


def timestamped_url(url, position=None):
    if position is None:return url
    seconds=float(position)
    if not math.isfinite(seconds) or seconds<0:return url
    parsed=urlparse(url)
    host=(parsed.hostname or '').lower()
    query=parse_qsl(parsed.query,keep_blank_values=True)
    parts=parsed.path.strip('/').split('/')
    video=None
    if host in ('youtu.be','www.youtu.be'):
        video=parts[0]
    elif host in ('youtube.com','www.youtube.com','m.youtube.com','music.youtube.com'):
        if parsed.path=='/watch':video=dict(query).get('v')
        elif len(parts)>1 and parts[0] in ('shorts','live','embed'):video=parts[1]
    if not video or not re.fullmatch(r'[A-Za-z0-9_-]{11}',video):return url
    query=[(k,v) for k,v in query if k not in ('v','t','start','time_continue')]
    return urlunparse(('https','www.youtube.com','/watch','',
        urlencode([('v',video),*query,('t',str(math.floor(seconds))+'s')]),''))


def copy_url(url, position=None):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or any(c in url for c in '\r\n\0'):
        raise ValueError('No article or video URL to copy')
    url=timestamped_url(url,position)
    # Passing the URL on stdin preserves query strings and never interprets shell syntax.
    subprocess.run(['wl-copy', '--type', 'text/plain;charset=utf-8'], input=url.encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=3)


if __name__ == '__main__':
    try:
        copy_url(sys.argv[1],sys.argv[2] if len(sys.argv)>2 else None)
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        print('Could not copy URL: '+str(error), file=sys.stderr)
        sys.exit(1)
