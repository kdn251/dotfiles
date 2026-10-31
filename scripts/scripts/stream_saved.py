"""Validate and append a manually entered streamer without duplicate entries."""
import fcntl
import re
from pathlib import Path
from urllib.parse import urlparse

FILES={'Twitch':'twitch_master_list.txt','Kick':'kick_channels.tsv','YouTube':'youtube_live_channels.tsv','Rumble':'rumble_channels.tsv'}
BASES={'Twitch':'https://www.twitch.tv/','Kick':'https://kick.com/','YouTube':'https://www.youtube.com/@','Rumble':'https://rumble.com/c/'}


def parse(text):
    text=text.strip();service='Twitch'
    if len(text)>2 and text[1]=='/' and text[0].lower() in 'tky r'.replace(' ',''):
        service={'t':'Twitch','k':'Kick','y':'YouTube','r':'Rumble'}[text[0].lower()];text=text[2:]
    if text.startswith(('https://','http://')):
        url=urlparse(text);host=(url.hostname or '').removeprefix('www.')
        service={'twitch.tv':'Twitch','kick.com':'Kick','youtube.com':'YouTube','rumble.com':'Rumble'}.get(host)
        if not service:raise ValueError('Enter a Twitch, Kick, YouTube or Rumble channel.')
        if url.query or url.fragment:raise ValueError('Enter a channel URL, not a video link.')
        text=url.path.strip('/')
        if service=='Rumble':text=text.removeprefix('c/')
        if service=='YouTube' and text.startswith('channel/'):
            ident=text.split('/')
            if len(ident)!=2 or not re.fullmatch(r'UC[\w-]+',ident[1]):raise ValueError('Enter a channel URL.')
            return service,ident[1],'https://www.youtube.com/channel/'+ident[1]
    text=text.lstrip('@').rstrip('/')
    pattern=r'[A-Za-z0-9_]{1,25}' if service=='Twitch' else r'[A-Za-z0-9_.-]+'
    if not re.fullmatch(pattern,text):raise ValueError('Enter a username or channel URL, not a video link.')
    if service in ('Twitch','Kick'):text=text.lower()
    return service,text,BASES[service]+text


def save(text, directory=None):
    service,name,url=parse(text)
    path=(Path(directory) if directory else Path.home()/'scripts')/FILES[service]
    with path.open('a+') as f:
        fcntl.flock(f,fcntl.LOCK_EX)
        f.seek(0);contents=f.read()
        for line in contents.splitlines():
            parts=line.strip().split()
            if not parts or parts[0].startswith('#'):continue
            if parts[0].casefold()==name.casefold() or (len(parts)>1 and parts[1].rstrip('/').casefold()==url.casefold()):
                return name,False
        if contents and not contents.endswith('\n'):f.write('\n')
        f.write(name+('' if service=='Twitch' else '\t'+url)+'\n')
    return name,True
