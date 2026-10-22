#!/usr/bin/env python3
"""Waybar artwork preview. Deliberately separate from live agent status."""
import argparse
import json
import pathlib
import time

SETTINGS = pathlib.Path.home()/'.config/agent-attention/mascot-preview.json'
THEMES = ('both', 'calcifer', 'sisyphus')
MODES = ('cycle', 'working', 'attention')

def settings():
    try:
        data = json.loads(SETTINGS.read_text())
        return {'theme': data.get('theme', 'both'), 'mode': data.get('mode', 'cycle')}
    except (OSError, ValueError):
        return {'theme': 'both', 'mode': 'cycle'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('watch', 'next', 'state', 'select'))
    parser.add_argument('theme', nargs='?', choices=THEMES)
    args = parser.parse_args()
    if args.action != 'watch':
        data = settings()
        if args.action == 'next': data['theme'] = THEMES[(THEMES.index(data['theme'])+1)%len(THEMES)]
        elif args.action == 'state': data['mode'] = MODES[(MODES.index(data['mode'])+1)%len(MODES)]
        else:
            if args.theme is None: parser.error('select needs a theme')
            data['theme'] = args.theme
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        tmp = SETTINGS.with_suffix('.tmp'); tmp.write_text(json.dumps(data)+'\n'); tmp.replace(SETTINGS)
        return
    if args.theme not in ('calcifer', 'sisyphus'): parser.error('watch needs one mascot')
    try:
        while True:
            data = settings(); now = time.monotonic()
            state = data['mode'] if data['mode'] in MODES[1:] else MODES[1+int(now//8)%2]
            visible = data['theme'] in ('both', args.theme)
            name = args.theme.capitalize()
            text = '·' if visible else ''
            tooltip = (f'<b>{name} · preview</b>\n'
                       f'{"Working" if state == "working" else "Needs attention"} — simulated, not live agent status\n'
                       'Left click: both / Calcifer / Sisyphus\nRight click: cycle / working / attention')
            print(json.dumps({'text': text, 'class': [state, 'f'+str(int(now*12)%24)],
                              'tooltip': tooltip}), flush=True)
            time.sleep(1/12)
    except (BrokenPipeError, KeyboardInterrupt):
        pass

if __name__ == '__main__': main()
