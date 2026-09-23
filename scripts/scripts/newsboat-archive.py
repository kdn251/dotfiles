#!/usr/bin/env python3
"""Open the newest archived article, falling back to lookup if absent."""
import os
from pathlib import Path
import sys
from urllib.parse import quote, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def archive_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Select an article with a web link.')
    return 'https://archive.ph/newest/' + quote(url, safe=':/')


def resolve_archive(url):
    newest = archive_url(url)
    try:
        with urlopen(Request(newest, method='HEAD'), timeout=4) as response:
            return response.url
    except HTTPError as error:
        if error.code == 404:
            return 'https://archive.ph/' + quote(url, safe=':/')
    except (URLError, TimeoutError):
        pass
    # Let the browser handle network challenges rather than treating them as
    # proof that the article has no snapshot.
    return newest


if __name__ == '__main__':
    original = sys.argv[1]
    target = resolve_archive(original)
    os.environ['NEWSBOAT_HISTORY_URL'] = original
    browser = Path(__file__).resolve().with_name('newsboat-brave-app.sh')
    os.execv(str(browser), [str(browser), target])
