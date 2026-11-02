import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'

class ScheduledJobsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), XDG_RUNTIME_DIR=str(self.home),
                        XDG_STATE_HOME=str(self.home / 'state'), PATH=str(self.bin)+':/usr/bin:/bin')

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n'+body+'\n')
        path.chmod(0o755)

    def test_refresh_uses_custom_binary_and_reports_failure(self):
        custom = self.home / '.local/lib/newsboat-paged/newsboat'
        custom.parent.mkdir(parents=True)
        custom.write_text('#!/bin/sh\necho custom-refresh-failed >&2\nexit 7\n')
        custom.chmod(0o755)
        self.tool('newsboat', 'exit 99')
        result = subprocess.run(['bash',str(SCRIPTS/'newsboat-refresh.sh')],env=self.env,capture_output=True)
        self.assertEqual(result.returncode,7)
        log = self.home/'state/newsboat/refresh.log'
        self.assertIn('custom-refresh-failed',log.read_text())
        self.assertFalse((log.parent/'last-refresh-success').exists())

    def test_starred_api_suffix_and_empty_result(self):
        credentials = self.home/'.newsboat/miniflux_creds'
        credentials.parent.mkdir()
        credentials.write_text('MINIFLUX_URL=https://example.test/v1\nMINIFLUX_USER=test\nMINIFLUX_PASS=test\n')
        self.tool('curl', '''for arg in "$@"; do
case "$arg" in
https://example.test/v1/entries*) printf '%s' '{"entries":[]}'; exit 0;;
esac
done
exit 22''')
        self.tool('sleep', 'exit 0')
        self.tool('notify-send','exit 0')
        (self.home/'scripts').mkdir()
        helper = self.home/'scripts/update-downloaded-query.sh'
        helper.write_text('#!/bin/sh\nexit 0\n');helper.chmod(0o755)
        result = subprocess.run(['bash',str(SCRIPTS/'auto-download-starred.sh')],env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertIn('Starting auto-download of 0 starred', (credentials.parent/'auto-download.log').read_text())
        self.tool('curl','exit 22')
        result = subprocess.run(['bash',str(SCRIPTS/'auto-download-starred.sh')],env=self.env,capture_output=True)
        self.assertNotEqual(result.returncode,0)

    def test_package_backup_leaves_unrelated_staging_intact(self):
        repo = self.home/'dotfiles';repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git','-C',str(repo),*args],env=self.env,stderr=subprocess.DEVNULL,text=True)
        git('init','-b','main');git('config','user.name','Test');git('config','user.email','test@example.invalid')
        for name in ('pacman-packages.txt','aur-packages.txt','note.txt'):(repo/name).write_text('original\n')
        git('add','.');git('commit','-m','Initial')
        remote = self.home/'remote.git'
        subprocess.run(['git','init','--bare',str(remote)],env=self.env,check=True,capture_output=True)
        git('remote','add','origin',str(remote));git('push','-u','origin','main')
        (repo/'note.txt').write_text('unrelated staged edit\n');git('add','note.txt')
        self.tool('pacman','printf "package\\n"')
        result = subprocess.run(['bash',str(SCRIPTS/'backup-packages.sh')],env=self.env,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr.decode())
        self.assertEqual(git('diff','--cached','--name-only').strip(),'note.txt')
        self.assertEqual(set(git('diff-tree','--no-commit-id','--name-only','-r','HEAD').split()),{'pacman-packages.txt','aur-packages.txt'})

if __name__ == '__main__':unittest.main()
