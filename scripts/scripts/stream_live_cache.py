"""Shared live-channel cache; picker reads never need a network request."""
import json
import os
import sys
import time


class OfflineError(ValueError):
    pass


def update_live_list(channels, cache, fetcher):
    try:
        previous = json.loads(cache.read_text())
    except (OSError, ValueError):
        previous = {}
    current = {}
    now = time.time()
    for line in channels.read_text().splitlines():
        fields = line.split('#', 1)[0].split()
        if len(fields) != 2:
            continue
        name, url = fields
        try:
            stream = fetcher(url)
            current[name] = dict(stream, channel=url, checked_at=now)
        except OfflineError:
            pass
        except Exception as error:
            print(f'{name}: live check failed: {error}', file=sys.stderr)
            old = previous.get(name, {})
            # Keep a recent live result through a brief network failure, but
            # never leave an old live entry around indefinitely.
            if old.get('channel') == url and now - old.get('checked_at', 0) < 900:
                current[name] = old
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_name(f'{cache.name}.{os.getpid()}.tmp')
    temporary.write_text(json.dumps(current))
    temporary.replace(cache)



def menu(cache, service):
    try:
        items = json.loads(cache.read_text())
    except (OSError, ValueError):
        return
    for name, item in items.items():
        if time.time() - item.get('checked_at', 0) < 900:
            print(f'00000\t{name.lower()} ({service.lower()})\t{name} ({service})\t{item.get("icon", "")}')
