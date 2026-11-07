#!/usr/bin/env python3
"""Install the pinned Apple emoji conversion used by stream-title-color.py."""
import hashlib
from pathlib import Path
import tempfile
from urllib.request import urlopen

URL = 'https://github.com/samuelngs/apple-emoji-ttf/releases/download/macos-26-20260722-484daf4e/AppleColorEmoji-Linux.ttf'
SHA256 = 'e37c7af6265ac4a0af6d57bc65e86109a776d9966e8343334557f63da482516f'

def main():
    target = Path.home()/'.local/share/mpv/fonts/AppleColorEmoji.ttf'
    if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == SHA256:
        print('Apple emoji font is already installed.')
        return
    with urlopen(URL, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != SHA256:
        raise ValueError('Downloaded font did not match the pinned checksum')
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as output:
        output.write(data)
        temporary = Path(output.name)
    temporary.replace(target)
    print('Installed Apple emoji font for MPV.')

if __name__ == '__main__':
    main()
