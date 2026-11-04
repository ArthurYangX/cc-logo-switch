import json
import tempfile
import unittest
from pathlib import Path
from png_to_claude_code.manage import activate, restore, sha256


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "claude"
        self.target.write_bytes(b"original with user customizations")
        self.original = self.target.read_bytes()
        self.expected = sha256(self.target)
        self.candidate = self.root / "candidate"
        self.candidate.write_bytes(b"new pixel header")
        self.candidate.chmod(0o755)
        self.state = self.root / "state" / "installation.json"

    def test_install_and_restore_preserve_existing_customizations(self):
        result = activate(self.candidate, self.target, self.state, self.expected)
        self.assertEqual(self.target.read_bytes(), b"new pixel header")
        self.assertEqual(Path(result["backup"]).read_bytes(), self.original)
        restore(self.state)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(json.loads(self.state.read_text())["status"], "restored")

    def test_install_refuses_concurrently_changed_source(self):
        self.target.write_bytes(b"updated elsewhere")
        with self.assertRaises(ValueError):
            activate(self.candidate, self.target, self.state, self.expected)
        self.assertEqual(self.target.read_bytes(), b"updated elsewhere")
        self.assertFalse(self.state.exists())

    def test_restore_refuses_newer_binary(self):
        activate(self.candidate, self.target, self.state, self.expected)
        self.target.write_bytes(b"newer Claude version")
        with self.assertRaises(ValueError):
            restore(self.state)
        self.assertEqual(self.target.read_bytes(), b"newer Claude version")

    def test_restore_refuses_corrupt_backup(self):
        result = activate(self.candidate, self.target, self.state, self.expected)
        Path(result["backup"]).write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            restore(self.state)
        self.assertEqual(self.target.read_bytes(), b"new pixel header")
