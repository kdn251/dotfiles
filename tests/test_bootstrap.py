"""Exercise restore behavior without package installs, sudo, or the real home."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cron_restore', ROOT/'bootstrap/cron.py')
cron = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cron)


class BootstrapTests(unittest.TestCase):
    def test_cron_preserves_unrelated_jobs_and_reruns(self):
        existing = 'MAILTO=me@example.invalid\n0 1 * * * /custom/job\n'
        template = (ROOT/'crontab_knaught').read_text()
        merged = cron.merge(existing, template, '/home/test', 1234)
        self.assertIn(existing, merged)
        self.assertNotIn('backup-packages.sh', merged)
        self.assertNotIn('update-packages.sh', merged)
        self.assertNotIn('/home/knaught', merged)
        self.assertNotIn('/run/user/1000', merged)
        self.assertIn('/run/user/1234', merged)
        self.assertEqual(merged, cron.merge(merged, template, '/home/test', 1234))

    def test_cron_rejects_broken_marker(self):
        with self.assertRaises(ValueError):
            cron.merge(cron.START, '', '/home/test', 1234)

    def test_fresh_home_stow_and_rerun(self):
        packages = (ROOT/'bootstrap/stow-packages.txt').read_text().split()
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            command = ['stow', '--no-folding', '-d', str(ROOT), '-t', str(home), *['--ignore=' + s for s in (ROOT/'bootstrap/stow-ignore.txt').read_text().splitlines()], *packages]
            for _ in range(2):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
            for rel in ['.zshrc', '.config/hypr/hyprland.lua', '.local/bin/hyprctl',
                        '.config/systemd/user/newsboat-maintenance.timer', 'scripts/sound-panel.py']:
                self.assertTrue((home/rel).is_file(), rel)
            for rel in ['etc', 'tests', 'windows', 'patches', 'browser-extension']:
                self.assertFalse((home/rel).exists(), rel)
            self.assertFalse(list(home.rglob('*.before-*')))
            pi_spec = importlib.util.spec_from_file_location('pi_setup', ROOT/'setup-pi.py')
            pi_setup = importlib.util.module_from_spec(pi_spec)
            pi_spec.loader.exec_module(pi_setup)
            pi_setup.configure(home, install_packages=False)
            pi_setup.configure(home, install_packages=False)

    def test_stow_conflict_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home/'.zshrc').write_text('my existing config')
            result = subprocess.run(['stow', '--no-folding', '-d', str(ROOT), '-t', str(home), 'zsh'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((home/'.zshrc').read_text(), 'my existing config')


if __name__ == '__main__':
    unittest.main()
