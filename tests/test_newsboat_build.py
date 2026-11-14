"""Offline integration test of the real patch chain; compilation is stubbed.

NEWSBOAT_TEST_ARCHIVE=/path/to/r2.44.tar.gz python3 -m unittest discover -s tests -p test_newsboat_build.py -v
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = os.environ.get('NEWSBOAT_TEST_ARCHIVE')


@unittest.skipUnless(ARCHIVE, 'Set NEWSBOAT_TEST_ARCHIVE to the pinned Newsboat archive')
class NewsboatBuildTests(unittest.TestCase):
    def test_patch_chain_reruns_without_old_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            # Curl supplies the offline archive; all real checksum, extraction,
            # patch and install commands still run. No live binaries are changed.
            mocks = {
                'curl': '#!/bin/bash\ncp "$NEWSBOAT_TEST_ARCHIVE" "${@: -1}"\n',
                'make': '#!/bin/bash\nprintf "#!/bin/sh\\nexit 0\\n" > newsboat\n',
            }
            for name, content in mocks.items():
                path = bin_dir / name
                path.write_text(content)
                path.chmod(0o755)
            cache = root / 'cache' / 'newsboat-paged'
            old = cache / 'newsboat-r2.44' / 'include' / 'recentlibrary.h'
            old.parent.mkdir(parents=True)
            old.write_text('stale file from a previous patched build')
            env = dict(os.environ, HOME=str(root / 'home'), XDG_CACHE_HOME=str(root / 'cache'),
                       PATH=str(bin_dir) + os.pathsep + os.environ['PATH'])
            for _ in range(2):
                result = subprocess.run(['bash', str(ROOT / 'scripts/scripts/newsboat-build-paged.sh')],
                                        env=env, text=True, capture_output=True, timeout=120)
                self.assertEqual(result.returncode, 0, result.stdout[-6000:] + result.stderr[-2000:])
                self.assertTrue((root / 'home/.local/lib/newsboat-paged/newsboat').is_file())
                self.assertFalse(list(cache.glob('build.*')))
            self.assertEqual(old.read_text(), 'stale file from a previous patched build')


if __name__ == '__main__':
    unittest.main()
