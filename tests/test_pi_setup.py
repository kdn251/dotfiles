"""Run with: python3 -m unittest discover -s tests -p 'test_pi_*.py'."""
import importlib.util
import json
import shutil
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("setup_pi", ROOT / "setup-pi.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class PiSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        self.agent = self.home / ".pi/agent"
        self.agent.mkdir(parents=True)

    def test_clean_install_and_repeat(self):
        setup.configure(self.home, install_packages=False)
        scene = self.agent / "extensions/animation-scenes/mac-scene.ts"
        self.assertTrue(scene.is_symlink())
        self.assertEqual(scene.read_bytes(), (ROOT / "agents/.pi/agent/extensions/animation-scenes/mac-scene.ts").read_bytes())
        self.assertTrue((self.home / ".claude/skills/fix/SKILL.md").is_file())
        self.assertTrue((self.agent / "prompts/fix.md").is_file())
        self.assertFalse((self.agent / "settings.json").is_symlink())
        self.assertEqual(json.loads((self.agent / "calm.json").read_text()), {"enabled": True})
        setup.configure(self.home, install_packages=False)
        self.assertEqual(list(self.home.glob(".pi-config-backup-*")), [])

    def test_preserves_local_data_and_backs_up_settings(self):
        settings = self.agent / "settings.json"
        settings.write_text(json.dumps({"defaultModel": "local-model", "packages": ["npm:other-plugin"], "hideThinkingBlock": False}))
        (self.agent / "auth.json").write_text("private sentinel")
        (self.agent / "calm.json").write_text('{"enabled":false}')
        setup.configure(self.home, install_packages=False)
        updated = json.loads(settings.read_text())
        self.assertEqual(updated["defaultModel"], "local-model")
        self.assertEqual(updated["packages"], ["npm:other-plugin"])
        self.assertTrue(updated["hideThinkingBlock"])
        self.assertEqual((self.agent / "auth.json").read_text(), "private sentinel")
        self.assertFalse(json.loads((self.agent / "calm.json").read_text())["enabled"])
        backups = list(self.home.glob(".pi-config-backup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o700)
        self.assertFalse((backups[0] / ".pi/agent/auth.json").exists())

    def test_conflicting_extension_aborts_before_changes(self):
        extension = self.agent / "extensions/minimal-footer.ts"
        extension.parent.mkdir()
        extension.write_text("my custom footer")
        with self.assertRaisesRegex(ValueError, "Conflicting local file"):
            setup.configure(self.home, install_packages=False)
        self.assertEqual(extension.read_text(), "my custom footer")
        self.assertFalse((self.agent / "settings.json").exists())
        self.assertFalse((self.home / ".agents").exists())

    def test_identical_local_file_becomes_link_with_backup(self):
        extension = self.agent / "extensions/minimal-footer.ts"
        extension.parent.mkdir()
        extension.write_bytes((ROOT / "agents/.pi/agent/extensions/minimal-footer.ts").read_bytes())
        setup.configure(self.home, install_packages=False)
        self.assertTrue(extension.is_symlink())
        self.assertEqual(len(list(self.home.glob(".pi-config-backup-*/.pi/agent/extensions/minimal-footer.ts"))), 1)

    def test_ignored_runtime_files_in_checkout_are_never_linked(self):
        checkout = self.home / "checkout"
        shutil.copytree(ROOT / "agents", checkout / "agents", symlinks=True)
        shutil.copy2(ROOT / "pi-config.json", checkout / "pi-config.json")
        source = checkout / "agents/.pi/agent"
        (source / "auth.json").write_text("private source credentials")
        (source / "sessions").mkdir()
        (source / "sessions/private.jsonl").write_text("private session")
        (source / "extensions/herdr-agent-state.ts").write_text("machine-specific hook")
        with patch.object(setup, "ROOT", checkout):
            setup.configure(self.home, install_packages=False)
        self.assertFalse((self.agent / "auth.json").exists())
        self.assertFalse((self.agent / "sessions").exists())
        self.assertFalse((self.agent / "extensions/herdr-agent-state.ts").exists())

    def test_symlinked_destination_directories_and_repeat(self):
        for relative in [".pi/agent/extensions", ".pi/agent/prompts", ".claude/skills"]:
            target = self.home / relative
            physical = self.home / "storage/at/a/different/depth" / relative
            physical.mkdir(parents=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(physical)
        setup.configure(self.home, install_packages=False)
        self.assertTrue((self.agent / "extensions/minimal-footer.ts").is_file())
        self.assertTrue((self.agent / "prompts/fix.md").is_file())
        self.assertTrue((self.home / ".claude/skills/fix/SKILL.md").is_file())
        setup.configure(self.home, install_packages=False)
        self.assertEqual(list(self.home.glob(".pi-config-backup-*")), [])

    @patch.object(setup.subprocess, "run")
    @patch.object(setup.subprocess, "check_output", return_value="1.0.4\n")
    @patch.object(setup.shutil, "which", return_value="/bin/tool")
    def test_package_versions_and_security_override(self, _which, _version, run):
        setup.configure(self.home)
        expected = setup.read_object(ROOT / "pi-config.json")["packages"]
        self.assertEqual([call.args[0] for call in run.call_args_list[:3]], [["pi", "install", name] for name in expected])
        manifest = setup.read_object(self.agent / "npm/package.json")
        self.assertEqual(manifest["overrides"]["pi-web-access"]["@modelcontextprotocol/sdk"], "1.32.1")
        self.assertEqual(run.call_args_list[-1].args[0], ["npm", "audit", "--omit=dev"])


if __name__ == "__main__":
    unittest.main()
