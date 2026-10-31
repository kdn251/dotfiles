import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('supervisor',Path(__file__).parents[1]/'scripts/hyprlock-supervisor.py')
supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)

class UnlockRefreshTests(unittest.TestCase):
    def run_supervisor(self, status, error=None):
        child=Mock();child.wait.return_value=status
        selector=Mock();selector.get_map.return_value={}
        with patch.object(supervisor.subprocess,'Popen',return_value=child), \
                patch.object(supervisor.selectors,'DefaultSelector',return_value=selector), \
                patch.object(supervisor.subprocess,'run',side_effect=error) as launch:
            result=supervisor.main()
            return result,launch

    def test_unlock_starts_background_refresh(self):
        result,launch=self.run_supervisor(0)
        self.assertEqual(result,0)
        self.assertIn('--no-block',launch.call_args.args[0])

    def test_failed_lock_does_not_trigger_refresh(self):
        result,launch=self.run_supervisor(1)
        self.assertEqual(result,1);launch.assert_not_called()

    def test_refresh_failure_must_not_relock(self):
        for error in (OSError('offline'),subprocess.TimeoutExpired('systemctl',5)):
            result,_=self.run_supervisor(0,error)
            self.assertEqual(result,0)
