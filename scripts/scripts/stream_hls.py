"""Select a muxed best-quality rendition without probing every HLS variant."""
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def attributes(line):
    return {key: value.strip('"') for key, value in
            re.findall(r'([A-Z0-9-]+)=("[^"]*"|[^,]*)', line)}


def best_variant(manifest, base):
    if not manifest.lstrip().startswith('#EXTM3U'): return base
    # Separate audio/subtitle playlists require the master for track selection.
    for line in manifest.splitlines():
        if line.startswith('#EXT-X-MEDIA:'):
            data=attributes(line)
            if data.get('TYPE') in ('AUDIO','SUBTITLES') and data.get('URI'): return base
    candidates=[]
    pending=None
    for line in manifest.splitlines():
        line=line.strip()
        if line.startswith('#EXT-X-STREAM-INF:'):
            pending=attributes(line)
        elif line and not line.startswith('#') and pending is not None:
            data,pending=pending,None
            resolution=re.fullmatch(r'(\d+)x(\d+)',data.get('RESOLUTION',''))
            if not resolution:continue
            url=urljoin(base,line)
            if urlsplit(url).scheme!='https':continue
            try:
                rank=(int(resolution[2]),float(data.get('FRAME-RATE',0)),int(data.get('BANDWIDTH',0)))
            except ValueError:continue
            candidates.append((rank,url))
    return max(candidates,key=lambda item:item[0])[1] if candidates else base


def resolve_best(url, service):
    request=Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':f'https://{service.lower()}.com/'})
    with urlopen(request,timeout=3) as response:
        return best_variant(response.read(1024*1024).decode('utf-8'),response.url)
