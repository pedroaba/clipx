"""Launcher shim behavior when invoked through a symlink from another directory."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class LauncherTests(unittest.TestCase):
    """Run the real launcher script against temporary project layouts."""

    def setUp(self):
        """Create a user bin directory with a symlink to the project launcher."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.root = Path(__file__).resolve().parents[1]
        user_bin = self.folder / "user bin"
        user_bin.mkdir()
        self.link = user_bin / "clipx"
        self.link.symlink_to(self.root / "bin" / "clipx")
        self.cwd = self.folder / "unrelated directory"
        self.cwd.mkdir()

    def test_symlink_launch_resolves_project_and_uses_explicit_python_module(self):
        """A symlinked launch resolves the project root and prefers uv run python -m."""
        shim_dir = self.folder / "shims"
        shim_dir.mkdir()
        uv = shim_dir / "uv"
        uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
        uv.chmod(0o755)
        result = subprocess.run(
            [str(self.link), "show"], cwd=self.cwd,
            env={**os.environ, "PATH": str(shim_dir) + ":/usr/bin:/bin"},
            text=True, capture_output=True, check=True, timeout=5,
        )
        self.assertEqual(result.stdout.splitlines(),
                         ["run", "--project", str(self.root), "python", "-m", "clipx.main", "show"])

    def test_symlink_launch_without_uv_works_from_another_directory(self):
        """Without uv the launcher still runs from an unrelated directory without recursion."""
        fallback_path = "/usr/bin:/bin"
        if shutil.which("uv", path=fallback_path):
            self.skipTest("uv is installed in the system PATH")
        result = subprocess.run(
            [str(self.link), "--help"], cwd=self.cwd,
            env={**os.environ, "PATH": fallback_path},
            text=True, capture_output=True, check=True, timeout=5,
        )
        self.assertIn("clipboard history manager", result.stdout)
        self.assertNotIn("recursively invoked", result.stderr)


if __name__ == "__main__":
    unittest.main()
