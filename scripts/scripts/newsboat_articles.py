"""Self-contained, script-free offline reading pages for Newsboat."""
import base64
import hashlib
import html
import json
import os
import re
import sqlite3
from contextlib import closing
from pathlib import Path
import sys
import time
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET


def canonical(url):
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or any(c in url for c in '\t\r\n'):
        raise ValueError('Expected an HTTP article URL')
    return urldefrag(url)[0]


def key(url):
    return hashlib.sha256(canonical(url).encode()).hexdigest()


def path_for(url):
    from newsboat_media import ROOT
    return ROOT/'articles'/f'{key(url)}.html'


def find(url):
    try:
        path = path_for(url)
        return path if path.is_file() and not path.is_symlink() and path.stat().st_size else None
    except (OSError, ValueError):
        return None


def fetch(url, limit, accept):
    canonical(url)
    request = Request(url, headers={'User-Agent': 'Mozilla/5.0 (compatible; NewsboatOffline/1.0)', 'Accept': accept})
    with urlopen(request, timeout=15) as response:
        data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError('Content exceeds the offline download size limit')
        return data, response.headers.get_content_type(), response.url


def reddit_id(url):
    parsed = urlparse(url)
    if parsed.hostname not in {'reddit.com', 'www.reddit.com', 'old.reddit.com', 'new.reddit.com', 'np.reddit.com', 'm.reddit.com'}:
        return None
    match = re.search(r'/comments/([a-z0-9]+)(?:/|$)', parsed.path)
    return match[1] if match else None


def reddit_snapshot(url, seen=None):
    """Resolve post bodies and crossposts; feed navigation is not post content."""
    from lxml import html as lhtml
    post_id = reddit_id(url)
    seen = set() if seen is None else seen
    if not post_id or post_id in seen or len(seen) >= 5:
        raise ValueError('The Reddit feed contains only links, not the post text')
    seen.add(post_id)
    candidates = []
    cache = Path(os.environ.get('NEWSBOAT_CACHE', Path.home()/'.newsboat/cache.db'))
    try:
        with closing(sqlite3.connect(cache.as_uri()+'?mode=ro', uri=True, timeout=1)) as db:
            candidates.extend((title, content) for link, title, content in db.execute(
                'SELECT url,title,content FROM rss_item WHERE url LIKE ? ORDER BY id DESC',
                ('%/comments/'+post_id+'%',)) if reddit_id(link) == post_id and content)
    except sqlite3.Error:
        pass
    state = Path(os.environ.get('XDG_STATE_HOME', Path.home()/'.local/state'))/'newsboat'
    try:
        candidates.extend((row['title'], row['content']) for row in json.loads((state/'starred-items.json').read_text())
                          if reddit_id(row.get('url','')) == post_id and row.get('content'))
    except (OSError, ValueError, KeyError):
        pass
    # A single-post RSS entry can supply the original body for a crosspost
    # that isn't in the local cache. Never treat a blocked/error page as text.
    if not candidates:
        try:
            feed_url = f'https://www.reddit.com/comments/{post_id}/.rss?limit=1'
            raw, mime, _ = fetch(feed_url, 4*1024*1024, 'application/atom+xml,application/xml')
            feed = ET.fromstring(raw)
            ns = {'a':'http://www.w3.org/2005/Atom'}
            for entry in feed.findall('a:entry', ns):
                if entry.findtext('a:id', '', ns) == 't3_'+post_id:
                    candidates.append((entry.findtext('a:title', '', ns), entry.findtext('a:content', '', ns)))
                    break
        except (OSError, ValueError, ET.ParseError):
            pass
    for title, content in candidates:
        root = lhtml.fragment_fromstring(content, create_parent='div')
        links = root.xpath('.//a[normalize-space(text())="[link]"]/@href')
        # Remove Reddit's standard feed footer before checking for real text.
        footer = content.rfind('submitted by')
        body = content[:footer] if footer >= 0 and '[comments]' in content[footer:] else content
        cleaned = lhtml.fragment_fromstring(body or '<div></div>', create_parent='div')
        text = cleaned.text_content().strip()
        if text and text not in {'[removed]', '[deleted]'} or cleaned.xpath('.//img'):
            return title, body
        for link in links:
            if reddit_id(link) and reddit_id(link) != post_id:
                _, original = reddit_snapshot(link, seen)
                return title, '<p>Crossposted from <a href="'+html.escape(link,quote=True)+'">the original Reddit post</a>.</p>'+original
    raise ValueError('Reddit supplied no post text, and the original could not be fetched. No offline copy was saved')


def reddit_comment_parents(post_id, rows):
    """A focused RSS thread with context=1 contains the direct parent first."""
    from newsboat_media import STATE, atomic_write
    from urllib.error import HTTPError
    cache = STATE.parent/'reddit-comment-parents'/(post_id+'.json')
    try: parents = json.loads(cache.read_text())
    except (OSError, ValueError): parents = {}
    deadline = time.monotonic()+240
    ns = {'a':'http://www.w3.org/2005/Atom'}
    for row in rows:
        ident = row['id']
        if ident in parents: continue
        if time.monotonic() >= deadline: break
        endpoint = row['url'].split('?')[0].rstrip('/')+'/.rss?context=1&limit=10'
        try:
            raw, _, _ = fetch(endpoint, 4*1024*1024, 'application/atom+xml')
            entries = ET.fromstring(raw).findall('a:entry', ns)
            ids = [entry.findtext('a:id','',ns) for entry in entries]
            comments = [value for value in ids if value.startswith('t1_')]
            if 't3_'+post_id not in ids or ident not in comments: continue
            # With one ancestor requested, the focused comment is first for a
            # top-level comment, or second immediately after its parent.
            if comments[0] == ident: parents[ident] = 't3_'+post_id
            elif len(comments)>1 and comments[1] == ident: parents[ident] = comments[0]
            atomic_write(cache, json.dumps(parents))
        except HTTPError as error:
            if error.code in {403,429}: break
        except (OSError, ValueError, ET.ParseError):
            pass
        time.sleep(2)
    return parents


def reddit_rss_tree(rows, parents, post_id):
    by_id = {row['id']:row for row in rows}
    children = {}
    roots = []
    for row in rows:
        parent = parents.get(row['id'])
        if parent in by_id and parent != row['id']:
            children.setdefault(parent, []).append(row)
        else: roots.append(row)
    visited = set()
    def render(row, rooted=False):
        if row['id'] in visited:return ''
        visited.add(row['id'])
        rooted = rooted or parents.get(row['id']) == 't3_'+post_id
        kind = 'yes' if rooted else 'partial'
        return ('<blockquote data-thread-known="'+kind+'"><p>'+row['label']+'</p>'+row['body']+
                ''.join(render(child,rooted) for child in children.get(row['id'],[]))+'</blockquote>')
    content = ''.join(render(row) for row in roots)
    content += ''.join(render(row) for row in rows if row['id'] not in visited)
    return content


def reddit_rss_comments(url):
    """Reddit's public thread feed remains usable when anonymous JSON is blocked.

    Atom provides comment bodies and permalinks, but no parent IDs or scores.
    Preserve feed order rather than inventing a reply hierarchy.
    """
    post_id = reddit_id(url)
    if not post_id:
        raise ValueError('Not a Reddit comment thread')
    endpoint = f'https://www.reddit.com/comments/{post_id}/.rss?limit=200&sort=top'
    raw, mime, _ = fetch(endpoint, 12*1024*1024, 'application/atom+xml,application/xml')
    feed = ET.fromstring(raw)
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    entries = feed.findall('a:entry', ns)
    if feed.tag != '{http://www.w3.org/2005/Atom}feed' or not any(
        entry.findtext('a:id', '', ns) == 't3_'+post_id for entry in entries
    ):
        raise ValueError('Reddit did not return the requested thread feed')
    seen = set()
    comments = []
    for entry in entries:
        ident = entry.findtext('a:id', '', ns)
        if not re.fullmatch(r't1_[a-z0-9]+', ident) or ident in seen:
            continue
        link = entry.find('a:link', ns)
        permalink = link.get('href', '') if link is not None else ''
        if reddit_id(permalink) != post_id:
            continue
        body = entry.findtext('a:content', '', ns)
        if not body.strip():
            continue
        seen.add(ident)
        author = entry.findtext('a:author/a:name', '[deleted]', ns).removeprefix('/').removeprefix('u/')
        label = '<strong>u/'+html.escape(author)+'</strong> · <a href="'+html.escape(permalink, quote=True)+'">View comment</a>'
        # The final article renderer sanitizes comment markup, like post text.
        comments.append(dict(id=ident,url=permalink,label=label,body=body))
        if len(comments) >= 200:
            break
    heading = f'<h2>Comments ({len(comments)} saved)</h2>'
    if not comments:
        return heading+'<p>No comments were returned by Reddit.</p>', []
    parents = reddit_comment_parents(post_id, comments)
    content = reddit_rss_tree(comments, parents, post_id)
    explanation = '<p>Saved Reddit discussion. Replies are grouped beneath their parent comments.</p>'
    if any(row['id'] not in parents or (parents[row['id']] != 't3_'+post_id and parents[row['id']] not in {r['id'] for r in comments}) for row in comments):
        explanation += '<p class="notice">Some thread context could not be retrieved. Those threads are marked incomplete.</p>'
    if len(comments) >= 200:
        content += '<p>Saved the first 200 comments returned by Reddit. Open the original post for the full discussion.</p>'
    return heading+explanation+content, []


def reddit_comments(url):
    """Save a bounded snapshot of the comments Reddit returns, including replies."""
    endpoint = canonical(url).split('?')[0].rstrip('/')+'.json?raw_json=1&limit=100&sort=top'
    try:
        raw, mime, _ = fetch(endpoint, 12*1024*1024, 'application/json')
        data = json.loads(raw)
        if not isinstance(data, list) or len(data) < 2:
            raise ValueError('Reddit did not return a comment thread')
        children = data[1]['data']['children']
    except (OSError, ValueError, KeyError, TypeError):
        try:
            return reddit_rss_comments(url)
        except (OSError, ValueError, ET.ParseError):
            pass
        return '<h2>Comments</h2><p>Comments could not be downloaded from Reddit. Open the original post to read the discussion.</p>', ['Reddit comments unavailable']
    count = 0
    truncated = False
    def comments(rows, depth=0):
        nonlocal count, truncated
        result = []
        for row in rows:
            if row.get('kind') == 'more':
                truncated = True
                continue
            if row.get('kind') != 't1':
                continue
            if count >= 200 or depth >= 10:
                truncated = True
                continue
            comment = row.get('data', {})
            body = comment.get('body_html')
            # raw_json normally supplies decoded HTML; legacy responses escape it.
            if body:
                if not body.lstrip().startswith('<'): body = html.unescape(body)
            else:
                body = '<p>'+html.escape(comment.get('body','')).replace('\n','<br>')+'</p>'
            count += 1
            author = html.escape(comment.get('author') or '[deleted]')
            score = comment.get('score')
            label = 'u/'+author+(f' · {score} points' if isinstance(score,int) else '')
            result.append('<blockquote><p><strong>'+label+'</strong></p>'+body)
            replies = comment.get('replies')
            if isinstance(replies,dict):
                result.append(comments(replies.get('data',{}).get('children',[]),depth+1))
            result.append('</blockquote>')
        return ''.join(result)
    content = comments(children)
    label = f'<h2>Comments ({count} saved)</h2><p>Snapshot sorted by top comments at download time.</p>'
    if not count: content = '<p>No comments were returned by Reddit.</p>'
    if truncated: content += '<p>Some comments or replies were not included. Open the original for the full discussion.</p>'
    return label+content, []


def post_body(raw):
    """Convert cached HTML to the same strict rendering vocabulary as articles."""
    from lxml import html as lhtml
    # Reddit wraps Markdown with <!-- SC_OFF --> / <!-- SC_ON -->.
    # Discard HTML comments before converting nodes, preserving their tails;
    # otherwise the converter turns comment contents into visible spans.
    root = lhtml.fragment_fromstring(raw, create_parent='div',
                                    parser=lhtml.HTMLParser(remove_comments=True))
    for element in root.xpath('.//script | .//style | .//iframe | .//form | .//object | .//embed'):
        element.drop_tree()
    if not root.text_content().strip() and not root.xpath('.//img'):
        raise ValueError('The cached Reddit post has no content to save')
    mapping = {'div':'main', 'section':'main', 'article':'main', 'p':'p', 'a':'ref',
               'img':'graphic', 'ul':'list', 'ol':'list', 'li':'item', 'blockquote':'quote',
               'pre':'code', 'code':'code', 'br':'lb', 'strong':'hi', 'b':'hi', 'em':'hi',
               'i':'hi', 'table':'table', 'tr':'row', 'td':'cell', 'th':'cell'}
    def convert(element):
        tag = element.tag if isinstance(element.tag,str) else 'span'
        out = ET.Element('head' if tag in {'h1','h2','h3','h4','h5','h6'} else mapping.get(tag,'span'))
        out.text, out.tail = element.text, element.tail
        if tag == 'a': out.set('target', element.get('href',''))
        if tag == 'blockquote' and element.get('data-thread-known') in {'yes','partial'}:
            out.set('thread-known', element.get('data-thread-known'))
        if tag == 'img':
            out.set('src', element.get('src',''))
            out.set('alt', element.get('alt',''))
        if tag in {'em','i'}: out.set('rend','italic')
        if out.tag == 'head': out.set('rend',tag)
        out.extend(convert(child) for child in element)
        return out
    return convert(root)


KEYS = """(() => {
  let lastG = 0;
  let frame = 0, destination = 0, position = 0, previousTime = 0;
  let heldKey = null, heldSince = 0;
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  function stopScroll() {
    cancelAnimationFrame(frame);
    frame = 0;
    previousTime = 0;
    heldKey = null;
  }
  function animateScroll(now) {
    const elapsed = previousTime ? Math.min(now - previousTime, 64) : 16;
    previousTime = now;
    // Drive held keys at the display's frame rate, not keyboard repeat rate.
    if (heldKey && now - heldSince > 100) {
      destination += (heldKey === 'j' ? 1 : -1) * 850 * elapsed / 1000;
    }
    destination = Math.max(0, Math.min(destination, document.documentElement.scrollHeight - innerHeight));
    const remaining = destination - position;
    if (Math.abs(remaining) <= 1 && !heldKey) {
      scrollTo(0, destination);
      stopScroll();
      return;
    }
    position += remaining * (1 - Math.exp(-elapsed / 55));
    scrollTo(0, position);
    frame = requestAnimationFrame(animateScroll);
  }
  function smoothScroll(distance) {
    if (reducedMotion.matches) { stopScroll(); scrollBy(0, distance); return; }
    // Repeated keys extend the destination without restarting the animation.
    // Reverse direction from the visible position instead of queued movement.
    if (!frame || Math.sign(distance) !== Math.sign(destination - scrollY)) {
      destination = position = scrollY;
    }
    destination = Math.max(0, Math.min(destination + distance, document.documentElement.scrollHeight - innerHeight));
    if (!frame) frame = requestAnimationFrame(animateScroll);
  }
  for (const name of ['wheel', 'touchstart', 'pointerdown', 'blur']) {
    window.addEventListener(name, stopScroll, {passive: true});
  }
  document.addEventListener('keyup', event => {
    if (event.key === heldKey) {
      heldKey = null;
      // A released key should settle promptly, without queued scrolling.
      if (performance.now() - heldSince > 100) {
        destination = position + Math.max(-40, Math.min(40, destination - position));
      }
    }
  });
  document.addEventListener('keydown', event => {
    const target = event.target;
    if (event.defaultPrevented || event.altKey || event.metaKey ||
        target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
    let distance = null;
    if (event.ctrlKey) {
      if (event.key === 'd') distance = innerHeight / 2;
      if (event.key === 'u') distance = -innerHeight / 2;
    } else {
      if (event.key === 'q') {
        event.preventDefault();
        if (window.newsboatSaveReading) window.newsboatSaveReading().finally(() => window.close());
        else window.close();
        return;
      }
      if (event.key === 'j' || event.key === 'k') {
        event.preventDefault();
        if (reducedMotion.matches) {
          scrollBy(0, event.key === 'j' ? 65 : -65);
        } else if (heldKey !== event.key) {
          heldKey = event.key;
          heldSince = performance.now();
          smoothScroll(event.key === 'j' ? 65 : -65);
        }
        return;
      }
      if (event.key === 'G') { event.preventDefault(); stopScroll(); scrollTo(0, document.documentElement.scrollHeight); return; }
      if (event.key === 'g') {
        event.preventDefault();
        const now = Date.now();
        if (now - lastG < 700) { stopScroll(); scrollTo(0, 0); lastG = 0; } else lastG = now;
        return;
      }
      lastG = 0;
    }
    if (distance !== null) { event.preventDefault(); smoothScroll(distance); }
  });
})();"""


COMMENT_THREAD_CSS = """
#article-comments .reddit-comment {border-left:3px solid #64717e;margin:22px 0;padding:0 0 0 14px;min-width:0;overflow-wrap:anywhere}
#article-comments .reddit-comment .reddit-comment {margin-left:36px;border-left-color:#72d5d1}
#article-comments .reddit-comment[data-depth="5"],
#article-comments .reddit-comment[data-depth="6"],
#article-comments .reddit-comment[data-depth="7"],
#article-comments .reddit-comment[data-depth="8"],
#article-comments .reddit-comment[data-depth="9"] {margin-left:0}
#article-comments .comment-thread-label {display:block;color:#adb7c2;font-size:13px;line-height:1.5;margin-bottom:5px;font-weight:normal}
#article-comments .reddit-comment > p:first-of-type {margin-top:0}
@media(max-width:600px){#article-comments .reddit-comment .reddit-comment{margin-left:18px;padding-left:10px}}
"""


def comment_thread_support(page):
    """Expose saved reply structure, including in previously downloaded pages."""
    if 'id="article-comments"' not in page:
        return page
    from lxml import html as lhtml
    document = lhtml.document_fromstring(page)
    section = document.get_element_by_id('article-comments', None)
    if section is None:
        return page
    unknown = 'reply nesting and scores are not supplied' in section.text_content()
    threads = {}
    for quote in section.iter('blockquote'):
        # Our saved comment header starts with the author's username. Ordinary
        # blockquotes inside a comment body remain quotations, not fake replies.
        header = quote.find('p')
        strong = header.find('strong') if header is not None else None
        label = strong.text_content() if strong is not None else ''
        author = re.match(r'u/([^\s·]+)', label)
        if author is None:
            continue
        parent = next((ancestor for ancestor in quote.iterancestors() if ancestor in threads), None)
        depth = threads[parent][0]+1 if parent is not None else 0
        threads[quote] = (depth, author[1])
        quote.set('class', 'reddit-comment')
        incomplete = quote.get('data-thread-known') == 'partial'
        unknown_row = unknown and quote.get('data-thread-known') not in {'yes','partial'}
        quote.set('data-depth', 'unknown' if unknown_row else str(depth))
        for old in header.xpath('./span[@class="comment-thread-label"]'):
            header.remove(old)
        if not unknown_row:
            badge = lhtml.Element('span', {'class':'comment-thread-label'})
            badge.text = (f'Reply level {depth} · replying to u/{threads[parent][1]}' if parent is not None else
                          'Top-level comment')
            if incomplete:
                badge.text = f'Reply to u/{threads[parent][1]}' if parent is not None else 'Thread context incomplete'
            header.insert(0, badge)
    for old in document.xpath('//style[@id="newsboat-comment-threads"]'):
        old.getparent().remove(old)
    style = lhtml.Element('style', id='newsboat-comment-threads')
    style.text = COMMENT_THREAD_CSS
    document.find('head').append(style)
    return lhtml.tostring(document, encoding='unicode', doctype='<!doctype html>')


def keyboard_support(page):
    page = comment_thread_support(page)
    digest = base64.b64encode(hashlib.sha256(KEYS.encode()).digest()).decode()
    page = re.sub(r'<script id="newsboat-keys">.*?</script>', '', page, flags=re.S)
    page = re.sub(r" script-src 'sha256-[^']+';", '', page)
    page = page.replace("default-src 'none';", "default-src 'none'; script-src 'sha256-"+digest+"';", 1)
    return page.replace('</body>', '<script id="newsboat-keys">'+KEYS+'</script></body>')


CSS = '''
:root {color-scheme:dark} body {margin:0;background:#171b20;color:#e4e7eb;font:19px/1.75 system-ui,sans-serif}
main {max-width:780px;margin:48px auto;padding:0 28px 80px} h1 {font-size:2rem;line-height:1.25}
h2,h3 {line-height:1.35;margin-top:2em} a {color:#72d5d1} img {max-width:100%;height:auto;border-radius:6px}
header {border-bottom:1px solid #39434d;padding-bottom:24px;margin-bottom:30px} .meta,.notice {color:#adb7c2;font-size:15px}
.notice {border-left:3px solid #72d5d1;padding:8px 16px} pre {overflow:auto;padding:16px;background:#222830}
blockquote {border-left:3px solid #64717e;margin-left:0;padding-left:20px} table {display:block;overflow:auto;border-collapse:collapse}
td,th {border:1px solid #39434d;padding:8px} @media(max-width:600px){main{margin-top:24px;padding:0 18px 40px}}
'''


def render(raw, url, title='', fetch_image=fetch, reddit=False, comments=''):
    import trafilatura
    from trafilatura.metadata import extract_metadata
    from lxml import html as lhtml
    if reddit:
        body = post_body(raw)
        metadata = None
        title = title or 'Reddit post'
    else:
        cleaned = lhtml.fromstring(raw)
        # Old sites often put the whole essay inside layout tables. Unwrap those
        # while retaining genuine data tables, and discard image-map navigation.
        for element in cleaned.xpath('//nav | //header | //footer | //img[@usemap] | //img[@height="1" or @width="1"]'):
            element.drop_tree()
        for element in cleaned.xpath('//a[img and not(normalize-space(text()))]'):
            target = urlparse(urljoin(url, element.get('href',''))).path
            if target in {'/', '/index.html', '/index.htm'}:
                element.drop_tree()
        for table in cleaned.xpath('//table[not(.//th)]'):
            if len(table.text_content()) > 800 and table.xpath('.//br | .//p | .//table'):
                for element in table.xpath('.//tr | .//td | .//tbody'):
                    element.drop_tag()
                table.drop_tag()
        xml = trafilatura.extract(cleaned, url=url, output_format='xml', include_images=True,
                                  include_links=True, include_formatting=True, include_comments=False)
        if not xml:
            raise ValueError('No readable article found; the site may require a browser or subscription')
        tree = ET.fromstring(xml)
        body = tree.find('main')
        text = ' '.join(body.itertext()) if body is not None else ''
        if len(text.split()) < 80:
            raise ValueError('Only a short excerpt was found; a full article could not be saved')
        # Common explicit paywall markers. Extraction cannot guarantee completeness
        # on every site, so the reading page labels the result as an extracted copy.
        if any(marker in text.lower() for marker in ('subscribe to continue reading', 'subscribe to read the full', 'already a subscriber?')):
            raise ValueError('A subscription prompt was found instead of the complete article')
        metadata = extract_metadata(raw, default_url=url)
        title = (metadata.title if metadata else None) or title or urlparse(url).hostname
    warnings = []
    images = {}
    image_bytes = 0
    deadline = time.monotonic() + 90

    def node(element):
        nonlocal image_bytes
        tag = element.tag
        if tag == 'graphic':
            source = urljoin(url, element.get('src', ''))
            if not element.get('src'):
                return ''
            if source not in images:
                try:
                    if len(images) >= 40 or image_bytes >= 40*1024*1024 or time.monotonic() > deadline:
                        raise ValueError('Image limit reached')
                    data, mime, _ = fetch_image(source, 8*1024*1024, 'image/*')
                    if mime not in {'image/jpeg','image/png','image/webp','image/gif','image/avif'}:
                        raise ValueError('Unsupported image format')
                    image_bytes += len(data)
                    images[source] = f'data:{mime};base64,'+base64.b64encode(data).decode()
                except (OSError, ValueError):
                    images[source] = ''
                    warnings.append('An image could not be saved')
            if not images[source]:
                return '<p class="notice">[Image unavailable offline]</p>'
            return '<img src="'+images[source]+'" alt="'+html.escape(element.get('alt',''),quote=True)+'">'
        attrs = ''
        if tag == 'quote' and element.get('thread-known') in {'yes','partial'}:
            attrs = ' data-thread-known="'+element.get('thread-known')+'"'
        mapped = {'main':'section','head':'h2','p':'p','list':'ul','item':'li','quote':'blockquote',
                  'code':'pre','table':'table','row':'tr','cell':'td','lb':'br','hi':'strong','del':'del','ref':'a'}
        out = mapped.get(tag, 'span')
        if tag == 'head' and element.get('rend') in {'h1','h2','h3','h4','h5','h6'}:
            out = element.get('rend')
        if tag == 'hi' and element.get('rend') in {'italic','italics','#i'}:
            out = 'em'
        if tag == 'ref':
            target = urljoin(url, element.get('target',''))
            if urlparse(target).scheme in {'http','https','mailto'}:
                attrs = ' href="'+html.escape(target,quote=True)+'" rel="noreferrer"'
            else:
                out = 'span'
        content = html.escape(element.text or '')+''.join(node(child)+html.escape(child.tail or '') for child in element)
        return f'<{out}{attrs}>{content}</{out}>'

    content = '<article id="article-content">'+node(body)+'</article>'
    if comments:
        content += '<section id="article-comments">'+node(post_body(comments))+'</section>'
    meta = ' · '.join(str(value) for value in (metadata.author if metadata else '', metadata.date if metadata else '', urlparse(url).hostname) if value)
    warning = '<p class="notice">Some images could not be saved. Missing images are marked below.</p>' if warnings else ''
    kind = 'Reddit post' if reddit else 'article'
    if reddit:
        warning += '<p class="notice">Saved from your feed. Saved post and comment snapshot. Use Open original for the live discussion and embedded videos.</p>'
    page = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
    page += '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'
    page += '<title>'+html.escape(title)+'</title><style>'+CSS+'</style></head><body><main><header><p class="meta">Saved '+kind+' · Available offline</p><h1>'+html.escape(title)+'</h1><p class="meta">'+html.escape(meta)+'</p>'
    page += '<a href="'+html.escape(url,quote=True)+'">Open original ↗</a><p class="meta">Extracted reading copy · Saved '+time.strftime('%B %d, %Y')+'</p></header>'+warning+content+'</main></body></html>'
    return keyboard_support(page), title, warnings


def download(url, title=''):
    from newsboat_media import atomic_write
    url = canonical(url)
    if reddit_id(url):
        title, raw = reddit_snapshot(url)
        final_url = url
        comments, comment_warnings = reddit_comments(url)
        page, title, warnings = render(raw, url, title, reddit=True, comments=comments)
        warnings.extend(comment_warnings)
    else:
        raw, mime, final_url = fetch(url, 12*1024*1024, 'text/html,application/xhtml+xml')
        if mime not in {'text/html','application/xhtml+xml'}:
            raise ValueError('This link is not an HTML article')
        page, title, warnings = render(raw, final_url, title)
    path = path_for(url)
    atomic_write(path, page)
    return dict(files=[str(path)], title=title, warnings=warnings, creator=urlparse(final_url).hostname,
                bytes=path.stat().st_size)


if __name__ == '__main__':
    try:
        print(json.dumps(download(sys.argv[1], sys.argv[2] if len(sys.argv)>2 else '')))
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
