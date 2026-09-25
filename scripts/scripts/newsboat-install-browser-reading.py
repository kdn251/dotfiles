#!/usr/bin/env python3
"""Register the native host and load the extension on Brave's next full start."""
import hashlib
import base64
import json
import os
from pathlib import Path


def install():
    scripts = Path(__file__).resolve().parent
    extension = scripts.parents[1]/'newsboat/browser-extension'
    manifest = json.loads((extension/'manifest.json').read_text())
    digest = hashlib.sha256(base64.b64decode(manifest['key'])).hexdigest()[:32]
    ident = ''.join(chr(97 + int(char, 16)) for char in digest)
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))
    hosts = config/'BraveSoftware/Brave-Browser/NativeMessagingHosts'
    hosts.mkdir(parents=True, exist_ok=True)
    host = scripts/'newsboat-browser-reading-host'
    host.chmod(0o755)
    (hosts/'local.newsboat.reading.json').write_text(json.dumps({
        'name': 'local.newsboat.reading', 'description': 'Newsboat article reading progress',
        'path': str(host), 'type': 'stdio',
        'allowed_origins': [f'chrome-extension://{ident}/']
    }, indent=2)+'\n')
    flags = config/'brave-flags.conf'
    lines = flags.read_text().splitlines() if flags.exists() else []
    for i, line in enumerate(lines):
        if line.startswith('--load-extension='):
            paths = line.split('=',1)[1].split(',')
            if str(extension) not in paths:
                lines[i] += ','+str(extension)
            break
    else:
        lines += ['', '# Remember reading positions for Newsboat articles.', '--load-extension='+str(extension)]
    flags.write_text('\n'.join(lines)+'\n')
    print('Installed Newsboat Reading Position. Fully restart Brave to activate it.')


if __name__ == '__main__':
    install()
