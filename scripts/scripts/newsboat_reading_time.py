"""Reading estimates from local article text; never fetch a page while browsing."""
from contextlib import closing
from html.parser import HTMLParser
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
from urllib.parse import urlparse
import newsboat_queue_time as timing


class Text(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[];self.hidden=[]
    def handle_starttag(self, tag, attrs):
        if tag in {'script','style','head','nav','header','footer'}:self.hidden.append(tag)
    def handle_endtag(self, tag):
        if tag in self.hidden:self.hidden.remove(tag)
    def handle_data(self, data):
        if not self.hidden:self.parts.append(data)


def article_key(url):
    parsed=urlparse(url)
    if parsed.scheme not in {'http','https'} or timing.media.identity(url):return None
    if (parsed.hostname or '').removeprefix('www.') in {'youtube.com','youtu.be','twitch.tv','clips.twitch.tv'}:return None
    return 'article:'+url


def estimate(url, allow_fetch=False):
    from newsboat_articles import find
    local=find(url)
    content=''
    if local:
        content=local.read_text(errors='replace')
    if not content:
        cache=Path(os.environ.get('NEWSBOAT_CACHE',Path.home()/'.newsboat/cache.db'))
        try:
            with closing(sqlite3.connect(cache.as_uri()+'?mode=ro',uri=True,timeout=.05)) as db:
                row=db.execute('SELECT content FROM rss_item WHERE url=? ORDER BY length(content) DESC LIMIT 1',(url,)).fetchone()
                if row:content=row[0] or ''
        except sqlite3.Error:pass
    if not content:
        content=next((r.get('content','') for r in timing.read('starred-items.json',[]) if r.get('url')==url),'')
    for name in ('commentary.db','favorites.db'):
        try:
            with closing(sqlite3.connect((timing.state()/name).as_uri()+'?mode=ro',uri=True,timeout=.05)) as db:
                row=db.execute('SELECT content FROM items WHERE url=?',(url,)).fetchone()
                if row and len(row[0] or '')>len(content):content=row[0]
        except sqlite3.Error:pass
    parser=Text();parser.feed(content)
    words=len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b",' '.join(parser.parts)))
    # Tiny feed link summaries are not useful estimates of the linked article.
    if words>=100:return words/220*60
    if allow_fetch:
        python=Path(os.environ.get('XDG_DATA_HOME',Path.home()/'.local/share'))/'newsboat/article-venv/bin/python'
        try:
            result=subprocess.run([str(python),str(Path(__file__).resolve()),url],capture_output=True,text=True,timeout=15,check=True)
            return float(result.stdout.strip())
        except (OSError,ValueError,subprocess.SubprocessError):pass
    return 0


def progress():
    try:
        with closing(sqlite3.connect((timing.state()/'reading-progress.db').as_uri()+'?mode=ro',uri=True,timeout=.02)) as db:
            return {url:max(0,min(1,float(fraction or 0))) for url,fraction in db.execute('SELECT url,fraction FROM articles')}
    except sqlite3.Error:return {}


def label(seconds, fraction=0):
    if not seconds:return ''
    minutes=math.ceil(seconds*(1-fraction)/60)
    return f'~{minutes}m' if minutes else '0m'


if __name__ == '__main__':
    from urllib.request import Request, urlopen
    import trafilatura
    url=sys.argv[1]
    with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=8) as response:
        raw=response.read(2*1024*1024)
    text=trafilatura.extract(raw,url=url,include_comments=False) or ''
    words=len(re.findall(r"\b[\w]+(?:['’-][\w]+)*\b",text))
    blocked=any(x in text.lower() for x in ('subscribe to continue reading','subscribe to read the full','already a subscriber?'))
    print(words/220*60 if words>=100 and not blocked else 0)
