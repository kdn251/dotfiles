"""Small, cached channel avatars shared by the live-stream picker."""
import hashlib
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen


def cache_avatar(channel, url):
    path = Path.home() / '.cache/stream-profiles' / (hashlib.sha256(channel.encode()).hexdigest()[:24] + '.png')
    if path.exists() and time.time() - path.stat().st_mtime < 86400:
        return str(path)
    if not url or not url.startswith('https://'):
        return str(path) if path.exists() else ''
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with urlopen(Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=10) as response:
            content = response.read(5 * 1024 * 1024)
        with tempfile.TemporaryDirectory(dir=path.parent) as folder:
            raw, png = Path(folder) / 'source', Path(folder) / 'avatar.png'
            raw.write_bytes(content)
            subprocess.run(['ffmpeg', '-nostdin', '-y', '-i', str(raw), '-vf',
                            'scale=70:70:force_original_aspect_ratio=increase,crop=70:70',
                            '-frames:v', '1', str(png)], check=True, timeout=15,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            png.replace(path)
    except Exception:
        pass  # A failed image request must not hide a live channel.
    return str(path) if path.exists() else ''
