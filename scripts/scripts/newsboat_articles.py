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
            feed_url = urldefrag(url)[0].split('?')[0].rstrip('/')+'/.rss'
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
    root = lhtml.fragment_fromstring(raw, create_parent='div')
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
      if (event.key === 'q') { event.preventDefault(); window.close(); return; }
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


def keyboard_support(page):
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


def render(raw, url, title='', fetch_image=fetch, reddit=False):
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

    content = node(body)
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
        page, title, warnings = render(raw+comments, url, title, reddit=True)
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
