"""Choose real lower-resolution renditions for muted theater panes."""
from urllib.request import Request,urlopen
from urllib.parse import urljoin,urlsplit
import re
from stream_hls import attributes


def hls_qualities(text,base,ceiling=480):
    # Keep external audio attached; a bare video rendition would lose sound.
    if any(line.startswith('#EXT-X-MEDIA:') and attributes(line).get('TYPE')=='AUDIO'
           and attributes(line).get('URI') for line in text.splitlines()):
        return base,base
    variants=[];pending=None
    for line in text.splitlines():
        line=line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'):pending=attributes(line)
        elif line and not line.startswith('#') and pending is not None:
            data,pending=pending,None
            size=re.fullmatch(r'(\d+)x(\d+)',data.get('RESOLUTION',''))
            url=urljoin(base,line)
            if not size or urlsplit(url).scheme!='https':continue
            try:variants.append(((int(size[2]),float(data.get('FRAME-RATE',0))),url))
            except ValueError:continue
    if not variants:return base,base
    low=[v for v in variants if v[0][0]<=ceiling]
    return max(variants)[1],(max(low) if low else min(variants))[1]


def resolve_hls_qualities(url,service):
    request=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':f'https://{service.lower()}.com/'})
    with urlopen(request,timeout=4) as response:
        return hls_qualities(response.read(1024*1024).decode('utf-8'),response.url)
