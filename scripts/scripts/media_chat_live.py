"""Read chat context only for the selected, running live player."""
from stream_player_identity import identity
import json
from pathlib import Path
import re
from urllib.parse import urlparse, parse_qs


def valid_chat_url(url):
    parsed=urlparse(url or '')
    if parsed.scheme!='https':return False
    if parsed.hostname=='kick.com':return bool(re.fullmatch(r'/popout/[a-zA-Z0-9_-]+/chat',parsed.path))
    if parsed.hostname=='rumble.com':return bool(re.fullmatch(r'/chat/popup/[0-9]+',parsed.path))
    if parsed.hostname in ('www.youtube.com','youtube.com'):
        return parsed.path=='/live_chat' and bool(re.fullmatch(r'[a-zA-Z0-9_-]{11}',parse_qs(parsed.query).get('v',[''])[0]))
    return False


def live_target(clients, focused):
    players=[c for c in clients if c.get('class','').lower()=='mpv']
    players.sort(key=lambda c:(c.get('address')!=focused,c.get('focusHistoryID',999)))
    if not players:return None
    try:
        args=Path(f"/proc/{int(players[0]['pid'])}/cmdline").read_bytes().split(b'\0')
        service=next((s for s in ('youtube','rumble','kick') if
                      f'--input-ipc-server=/tmp/mpv-{s}-live-ipc'.encode() in args),None)
        current = identity(players[0])
        if current: service = current[0].lower()
        if service not in ('youtube', 'rumble', 'kick'):return None
        root=Path.home()/'.cache'
        context=json.loads((root/f'{service}-live-player.json').read_text())
        url=context.get('chat_url')
        channel=context.get('channel','')
        # Upgrade metadata for a player launched before chat support was added.
        if not url:
            try:
                cached=json.loads((root/f'{service}-live.json').read_text())
                entry=next((v for v in cached.values() if v.get('url')==context.get('url')), {})
                url=entry.get('chat_url');channel=channel or entry.get('channel','')
            except (OSError,ValueError):pass
        if not url and service=='youtube':
            video=parse_qs(urlparse(context.get('url','')).query).get('v',[''])[0]
            url=f'https://www.youtube.com/live_chat?v={video}&is_popout=1'
        if not url and service=='kick':
            slug=urlparse(channel).path.strip('/')
            url=f'https://kick.com/popout/{slug}/chat'
        return dict(service=service,title=('YouTube' if service=='youtube' else service.title())+' live chat',url=url if valid_chat_url(url) else None)
    except (OSError,ValueError,KeyError,TypeError):return None
