#!/usr/bin/env python3
"""Copy an item's original web URL to the Wayland clipboard."""
import subprocess
import sys
from urllib.parse import urlparse


def copy_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or any(c in url for c in '\r\n\0'):
        raise ValueError('No article or video URL to copy')
    # Passing the URL on stdin preserves query strings and never interprets shell syntax.
    subprocess.run(['wl-copy', '--type', 'text/plain;charset=utf-8'], input=url.encode(),
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=3)


if __name__ == '__main__':
    try:
        copy_url(sys.argv[1])
    except (OSError, ValueError, IndexError, subprocess.SubprocessError) as error:
        print('Could not copy URL: '+str(error), file=sys.stderr)
        sys.exit(1)
