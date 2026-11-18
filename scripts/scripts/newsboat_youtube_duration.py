"""Read a video's public duration without extracting playable media formats."""
import json
import re
from urllib.request import Request, urlopen


def parse_duration(document, video_id):
    for match in re.finditer(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',document):
        try:data,_=json.JSONDecoder().raw_decode(document[match.end():])
        except ValueError:continue
        details=data.get('videoDetails',{})
        if details.get('videoId')!=video_id or details.get('isLive'):continue
        if data.get('playabilityStatus',{}).get('status')!='OK':continue
        try:seconds=int(details.get('lengthSeconds',0))
        except (ValueError,TypeError):continue
        if 0<seconds<604800:return seconds
    return 0


def fetch(video_id):
    request=Request('https://www.youtube.com/watch?v='+video_id,
                    headers={'User-Agent':'Mozilla/5.0','Accept-Language':'en-US,en;q=0.9'})
    try:
        with urlopen(request,timeout=3) as response:
            document=response.read(3*1024*1024).decode('utf-8',errors='replace')
        return parse_duration(document,video_id)
    except (OSError,ValueError):return 0
