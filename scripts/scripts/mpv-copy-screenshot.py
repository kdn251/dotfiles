#!/usr/bin/env python3
"""Copy the saved screenshot as PNG without changing or deleting the file."""
import io
from pathlib import Path
import subprocess
import sys
from PIL import Image


def copy(path):
    path=Path(path)
    with Image.open(path) as image:
        output=io.BytesIO()
        image.convert('RGBA').save(output,format='PNG')
    subprocess.run(['wl-copy','--type','image/png'],input=output.getvalue(),check=True,timeout=5)


if __name__=='__main__':copy(sys.argv[1])
