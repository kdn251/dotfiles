#!/usr/bin/env python3
"""Compatibility for old bindings; saved items now live only in Miniflux."""
import runpy
import sys
from pathlib import Path
# Old running Shelf windows must not unstar items merely because they are read.
if sys.argv[1:2] != ['consume']:
    runpy.run_path(str(Path(__file__).with_name('newsboat-starred.py')),run_name='__main__')
