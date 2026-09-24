"""Locally cached source names for synthetic and offline article lists."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from urllib.parse import urlparse


def feed_titles(state=None):
    state = state or Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
    try:
        return json.loads((state/'feed-titles.json').read_text())
    except (OSError, ValueError):
        return {}


def article_sources(cache, state=None):
    titles = feed_titles(state)
    try:
        with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True)) as db:
            return {url: title or titles.get(feed, '') for url, feed, title in db.execute(
                'SELECT i.url,i.feedurl,f.title FROM rss_item i LEFT JOIN rss_feed f ON f.rssurl=i.feedurl')}
    except sqlite3.Error:
        return {}


def source_label(url, name):
    host = urlparse(url).hostname
    icon = ' ' if host in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'} else ' ' if host in {'twitch.tv', 'www.twitch.tv', 'clips.twitch.tv'} else ''
    return icon + (name or '')
