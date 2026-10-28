"""Read rich stream labels locally; opening the picker never waits on a server."""
import json
from pathlib import Path


def load():
    result={}
    for service in ('twitch','youtube','rumble','kick'):
        try:
            data=json.loads((Path.home()/'.cache'/f'{service}-live.json').read_text())
            result[service[0]]={name.casefold():row for name,row in data.items()}
        except (OSError,ValueError,AttributeError):
            result[service[0]]={}
    return result


def details(label, identity, service, cache):
    name=identity.split()[0]
    data=cache.get(service,{}).get(name.casefold(),{})
    category=' '.join(str(data.get('category') or '').split())
    title=' '.join(str(data.get('title') or '').split())
    viewers=data.get('viewer_count')
    count=''
    if isinstance(viewers,(int,float)) and not isinstance(viewers,bool):
        count=(f'{viewers/1000:.1f}k' if viewers>=1000 else str(int(viewers)))+' watching'
    if not category and ' — ' in label:
        category=label.split(' — ',1)[1].split(' · ',1)[0]
    return name, category, title, count


def search_rank(query, name, category='', title=''):
    query=query.strip().lstrip('@').casefold()
    name=name.casefold()
    if not query:return 0
    if name==query:return 0
    if name.startswith(query):return 1
    if query in name:return 2
    # Keep abbreviation matching for names, but don't match scattered letters
    # across the much longer game/title fields.
    letters=iter(name)
    if all(any(letter==char for letter in letters) for char in query):return 3
    if query in category.casefold():return 4
    if query in title.casefold():return 5
    return None


def highlight(text, query, fuzzy=False, offset=0):
    from html import escape
    query=query.strip().lstrip('@').casefold()
    folded=''
    indices=[]
    for i,char in enumerate(text):
        part=char.casefold()
        folded+=part
        indices.extend([i]*len(part))
    marked=set()
    if query:
        start=folded.find(query)
        while start>=0:
            marked.update(indices[start:start+len(query)])
            start=folded.find(query,start+len(query))
        if not marked and fuzzy:
            cursor=0
            found=[]
            for char in query:
                at=folded.find(char,cursor)
                if at<0:break
                found.append(indices[at]);cursor=at+1
            else:marked.update(found)
    pairs=[(char,i in marked) for i,char in enumerate(text)]
    if offset and pairs:
        offset%=len(pairs)
        pairs=pairs[offset:]+pairs[:offset]
    result=[]
    active=False
    for char,hit in pairs:
        if hit!=active:
            result.append('<span foreground="#ebcb8b" weight="bold" underline="single">' if hit else '</span>')
            active=hit
        result.append(escape(char,quote=False))
    if active:result.append('</span>')
    return ''.join(result)


def playback_title(name, service, fallback=''):
    data=load().get(service[0].lower(),{}).get(name.casefold(),{})
    _, category, title, viewers=details(name,name,service[0].lower(),{service[0].lower():{name.casefold():data}})
    title=' '.join((fallback or title).split())
    info=' · '.join(part for part in (category,viewers) if part)
    heading=name+(' — '+info if info else '')
    return heading+(' | '+title if title and title.casefold()!=name.casefold() else '')


if __name__=='__main__':
    import sys
    print(playback_title(sys.argv[1],sys.argv[2],sys.argv[3] if len(sys.argv)>3 else ''))
