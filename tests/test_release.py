"""Regression checks for frozen subprocesses and release inputs."""
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from clipx.processes import module_command
from clipx.platforms.linux.clipboard import LinuxClipboardDriver
from clipx.platforms.macos.clipboard import MacOSClipboardDriver
from tools.release import architecture, checksums, project_version, validate_tag


class ReleaseTests(unittest.TestCase):
    """Verify frozen command construction, version tags and release artifacts."""

    def test_source_worker_keeps_python_module_command(self):
        """In a source checkout the worker launches through the current Python module."""
        with patch.object(sys, 'frozen', False, create=True):
            self.assertEqual(module_command('clipx.capture', 'history.db'),
                             [sys.executable, '-m', 'clipx.capture', 'history.db'])

    def test_frozen_drivers_launch_the_packaged_worker(self):
        """Frozen builds reuse the packaged executable for workers and internal commands."""
        with patch.object(sys, 'frozen', True, create=True), patch.object(sys, 'executable', '/app/clipx'):
            self.assertEqual(MacOSClipboardDriver().listener_command(Path('a b.db')),
                             ['/app/clipx', '_capture', 'a b.db', '--watch-macos'])
            with patch.dict(os.environ, {'DISPLAY': ':0'}):
                self.assertEqual(LinuxClipboardDriver().listener_command(Path('a b.db')),
                                 ['/app/clipx', '_capture', 'a b.db', '--watch-x11'])
            with patch.dict(os.environ, {'DISPLAY': ''}):
                self.assertEqual(LinuxClipboardDriver().listener_command(Path('a b.db')),
                                 ['wl-paste', '--type', 'text', '--watch', '/app/clipx', '_capture', 'a b.db'])
            self.assertEqual(module_command('clipx.main', 'show'), ['/app/clipx', 'show'])

    def test_release_tag_must_match_project_version(self):
        """An empty or matching tag passes while a mismatched version raises."""
        validate_tag('')
        validate_tag('v' + project_version())
        with self.assertRaises(ValueError):
            validate_tag('v999.0.0')

    def test_architecture_and_checksums(self):
        """Machine names map to release architectures and checksums match SHA-256 output."""
        with patch('tools.release.platform.machine', return_value='x86_64'):
            self.assertEqual(architecture(), 'amd64')
        with patch('tools.release.platform.machine', return_value='aarch64'):
            self.assertEqual(architecture(), 'arm64')
        with patch('tools.release.platform.machine', return_value='unknown'):
            with self.assertRaises(ValueError):
                architecture()
        with tempfile.TemporaryDirectory() as folder:
            artifact = Path(folder) / 'installer.deb'
            artifact.write_bytes(b'fixture')
            result = checksums([artifact], Path(folder), 'test')
            self.assertEqual(result.read_text(), hashlib.sha256(b'fixture').hexdigest() + '  installer.deb\n')

    def test_release_workflow_has_native_macos_and_container_linux(self):
        """The workflow builds both macOS architectures and publishes after Linux and macOS."""
        try:
            import yaml
        except ImportError:
            self.skipTest('Install the build dependency group to validate workflow YAML')
        root = Path(__file__).resolve().parents[1]
        workflow = yaml.safe_load((root / '.github/workflows/release.yml').read_text())
        runners = workflow['jobs']['macos']['strategy']['matrix']['include']
        self.assertEqual({item['arch'] for item in runners}, {'amd64', 'arm64'})
        self.assertTrue(all(item['runner'].startswith('macos-') for item in runners))
        self.assertEqual(set(workflow['jobs']['publish']['needs']), {'linux', 'macos'})
        compose = yaml.safe_load((root / 'compose.yaml').read_text())
        self.assertIn('linux-install-test', compose['services'])
        self.assertEqual(compose['services']['linux-build']['command'], ['linux'])
