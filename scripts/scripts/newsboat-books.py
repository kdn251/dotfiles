#!/usr/bin/env python3
"""Local PDF/EPUB library for Newsboat; books stay in their original folder."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, unquote
import newsboat_media as media
import newsboat_books_progress as progress

SCRIPTS = Path(__file__).resolve().parent
DIRECTORY = Path(os.environ.get('NEWSBOAT_BOOKS_DIR', Path.home()/'Books')).expanduser()
STATE = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
TITLE = '📚 Books'
PREFIX = 'query:'+TITLE+':'


def entries():
    DIRECTORY.mkdir(parents=True, exist_ok=True)
    rows = {}
    for path in DIRECTORY.rglob('*'):
        if path.suffix.lower() not in {'.pdf','.epub'} or not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(DIRECTORY.resolve()):
            continue
        url = resolved.as_uri()
        rows[url] = dict(url=url, title=path.stem, kind=path.suffix[1:].upper(),
                         id=hashlib.sha256(url.encode()).hexdigest())
    return sorted(rows.values(), key=lambda row: (row['title'].casefold(),row['url']))


def query(rows):
    terms = ' or '.join('link = '+json.dumps(row['url']) for row in rows)
    return json.dumps(PREFIX+(terms or 'link = "newsboat-books://empty"'),ensure_ascii=False)


def rebuild():
    rows = entries()
    with media.library_lock():
        media.atomic_write(STATE/'starred-urls.txt.books.count',str(len(rows))+'\n')
        lines = media.URLS.read_text().splitlines() if media.URLS.exists() else []
        lines = [line for line in lines if not line.startswith('"'+PREFIX)]
        vod = next((i for i,line in enumerate(lines) if line.startswith('"query:🎬 VODs:')),None)
        position = vod+1 if vod is not None else next((i for i,line in enumerate(lines) if line.startswith(('"query: Favorites:', '"query:🌎 All:'))),len(lines))
        lines.insert(position,query(rows))
        content = '\n'.join(lines)+'\n'
        if not media.URLS.exists() or media.URLS.read_text()!=content:
            media.atomic_write(media.URLS,content)
    return rows


def prepare_view(directory, rows):
    directory=Path(directory)
    rss=ET.Element('rss',version='2.0');channel=ET.SubElement(rss,'channel')
    for key,value in [('title',TITLE),('link','https://localhost/books'),('description','Local PDFs and EPUBs')]:
        ET.SubElement(channel,key).text=value
    for row in rows or [dict(title='No books yet — add PDFs or EPUBs to '+str(DIRECTORY),url='newsboat-books://empty',kind='',id='empty')]:
        item=ET.SubElement(channel,'item')
        for key,value in [('title',row['title']),('link',row['url']),('guid','book-'+row['id']),('author',row['kind'])]:
            ET.SubElement(item,key).text=value
    feed=directory/'books.xml'
    ET.ElementTree(rss).write(feed,encoding='utf-8',xml_declaration=True)
    (directory/'urls').write_text(feed.as_uri()+'\n')
    source=Path.home()/'.newsboat/config'
    if not source.exists():source=SCRIPTS.parents[1]/'newsboat/.newsboat/config'
    appearance={'color','highlight','highlight-article','scrolloff','text-width'}
    lines=[line for line in source.read_text().splitlines() if line.split() and line.split()[0] in appearance]
    lines += [line for line in source.read_text().splitlines() if line.startswith('bind 7 ')]
    browser='python3 '+shlex.quote(str(Path(__file__).resolve()))+' open %u'
    lines += ['show-read-feeds yes','show-read-articles yes','confirm-exit no',
              'article-sort-order title-asc','articlelist-title-format " %T"',
              'articlelist-format "%4w  %-4a │ %t"','browser '+json.dumps(browser),
              'bind-key j down','bind-key k up','bind-key G end','bind-key g home',
              'bind q articlelist hard-quit','bind H articlelist hard-quit',
              'bind o articlelist,searchresultslist open-in-browser-noninteractively',
              'bind O articlelist,searchresultslist open-in-browser-noninteractively',
              'bind <ENTER> articlelist,searchresultslist open-in-browser-noninteractively']
    config=directory/'config';config.write_text('\n'.join(lines)+'\n')
    binary=Path.home()/'.local/lib/newsboat-paged/newsboat'
    return [str(binary) if binary.exists() else 'newsboat','-q','-C',str(config),'-u',str(directory/'urls'),'-c',str(directory/'cache.db')]


def open_book(url):
    if url=='newsboat-books://empty':return
    parsed=urlparse(url)
    if parsed.scheme!='file' or parsed.netloc not in {'','localhost'}:
        raise ValueError('Select a local PDF or EPUB')
    path=Path(unquote(parsed.path)).resolve()
    if not path.is_relative_to(DIRECTORY.resolve()) or path.suffix.lower() not in {'.pdf','.epub'} or not path.is_file():
        raise ValueError('This book is no longer in '+str(DIRECTORY))
    subprocess.Popen(['zathura' if path.suffix.lower()=='.pdf' else 'foliate',str(path)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)


def show():
    rows=rebuild()
    with tempfile.TemporaryDirectory(prefix='newsboat-books-') as directory:
        command=prepare_view(directory,rows)
        env={k:v for k,v in os.environ.items() if not k.startswith('NEWSBOAT_')}
        if os.environ.get('NEWSBOAT_RANDOM_PROMPT_DIR'):
            env['NEWSBOAT_RANDOM_PROMPT_DIR']=os.environ['NEWSBOAT_RANDOM_PROMPT_DIR']
        env['NEWSBOAT_BOOKS_DIR']=str(DIRECTORY)
        env['NEWSBOAT_DOWNLOAD_STATUS']=str(progress.STATE/'status.tsv')
        progress.publish(rows,refresh=False)
        subprocess.run(command+['-x','reload'],env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
        with (Path(directory)/'config').open('a') as f:f.write('run-on-startup open\n')
        process=subprocess.Popen(command,env=env)
        try:
            while process.poll() is None:
                progress.publish(rows)
                try:process.wait(timeout=2)
                except subprocess.TimeoutExpired:pass
            progress.publish(rows)
            return process.returncode
        finally:
            if process.poll() is None:
                process.terminate();process.wait(timeout=5)


if __name__=='__main__':
    try:
        action=sys.argv[1] if len(sys.argv)>1 else 'show'
        if action=='show':sys.exit(show())
        elif action=='rebuild':rebuild()
        elif action=='open':open_book(sys.argv[2])
    except (OSError,ValueError,subprocess.SubprocessError) as error:
        subprocess.run(['notify-send','-a','Newsboat','-t','5000','Books unavailable',str(error)])
        sys.exit(1)
