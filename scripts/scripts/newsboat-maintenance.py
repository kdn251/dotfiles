#!/usr/bin/env python3
"""Refresh the Starred menu and safely maintain the download library."""
import importlib.util
import json
import sys
from pathlib import Path
from newsboat_miniflux import Client
import newsboat_download_cleanup as cleanup


def load_starred():
    spec = importlib.util.spec_from_file_location('newsboat_starred', Path(__file__).with_name('newsboat-starred.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    if sys.argv[1:2] == ['watched']:
        return 0 if cleanup.record(sys.argv[2],sys.argv[3],float(sys.argv[4])) else 1
    starred = load_starred()
    try:
        rows = Client().starred()
        starred.rebuild_query(rows)
        if sys.argv[1:2] != ['sync'] and cleanup.CONFIG.exists():
            settings = json.loads(cleanup.CONFIG.read_text())
            if settings.get('enabled'):
                removed = cleanup.cleanup([row['url'] for row in rows], settings['days'])
                if removed:
                    print(f'Removed {len(removed)} watched downloads')
        return 0
    except Exception:
        # An outage must never trigger unprotected cleanup.
        print('Miniflux unavailable; cleanup was skipped.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
