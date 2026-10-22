"""Platform boundaries: these tests must run without native desktop access."""
import importlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


class PlatformTests(unittest.TestCase):
    """Validate platform selection, migration and driver edge cases."""

    def test_factory_selects_platform_and_rejects_unsupported(self):
        """The factory maps linux and darwin and rejects unsupported systems."""
        from clipx.platforms import get_platform
        self.assertEqual(get_platform('linux').name, 'linux')
        self.assertEqual(get_platform('darwin').name, 'macos')
        with self.assertRaisesRegex(RuntimeError, 'suportado'):
            get_platform('win32')

    def test_importing_linux_does_not_import_appkit(self):
        """Selecting the Linux platform does not import macOS frameworks."""
        code = "from clipx.platforms import get_platform; get_platform('linux'); import sys; assert 'AppKit' not in sys.modules; assert 'Quartz' not in sys.modules"
        subprocess.run([sys.executable, '-c', code], check=True)

    def test_macos_paths_migrate_without_destroying_source_or_overwriting(self):
        """Legacy data is copied with a backup while an existing config is preserved."""
        from clipx.platforms.paths import PlatformPaths
        from clipx.storage import Storage
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            old = home / '.local/share/clipx/history.db'
            old.parent.mkdir(parents=True)
            Storage(old).add_clip('acentuação\nconteúdo')
            prefs = home / '.config/clipx/settings.json'
            prefs.parent.mkdir(parents=True)
            prefs.write_text('{"shortcuts": {}}')
            paths = PlatformPaths('darwin', home=home)
            paths.migrate_legacy()
            self.assertEqual(Storage(paths.data / 'history.db').get_clips()[0].content, 'acentuação\nconteúdo')
            self.assertTrue(old.exists())
            self.assertTrue((paths.data / 'history.db.pre-migration.bak').exists())
            (paths.config / 'settings.json').write_text('new preferences')
            paths.migrate_legacy()
            self.assertEqual((paths.config / 'settings.json').read_text(), 'new preferences')

    def test_macos_poll_only_reads_changes_and_skips_private_or_own_content(self):
        """Polling reads a change once and ignores concealed, transient or self-marked content."""
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver
        board = Mock()
        board.changeCount.return_value = 1
        board.types.return_value = ['public.utf8-plain-text']
        board.stringForType_.return_value = 'Olá\n世界'
        driver = MacOSClipboardDriver(pasteboard=board)
        sink = Mock()
        driver.poll(sink)
        driver.poll(sink)
        sink.save.assert_called_once_with('Olá\n世界')
        board.stringForType_.assert_called_once()
        for index, marker in enumerate(('org.nspasteboard.ConcealedType', 'org.nspasteboard.TransientType', 'org.clipx.self'), 2):
            board.changeCount.return_value = index
            board.types.return_value = [marker, 'public.utf8-plain-text']
            driver.poll(sink)
        self.assertEqual(board.stringForType_.call_count, 1)
        self.assertEqual(sink.save.call_count, 1)

    def test_macos_poll_discards_read_if_pasteboard_changes_during_read(self):
        """A change counter that moves during a read discards the stale value."""
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver
        board = Mock()
        board.changeCount.side_effect = [1, 2]
        board.types.return_value = ['public.utf8-plain-text']
        board.stringForType_.return_value = 'stale'
        sink = Mock()
        MacOSClipboardDriver(pasteboard=board).poll(sink)
        sink.save.assert_not_called()

    def test_macos_paste_denied_or_missing_target_never_posts_keys(self):
        """Without permission or a previous target no synthetic key events are posted."""
        from clipx.platforms.macos.desktop import MacOSDesktopDriver
        quartz = Mock()
        quartz.can_paste.return_value = False
        driver = MacOSDesktopDriver(appkit=Mock(), quartz=quartz, permissions=quartz)
        result = driver.paste_to_previous()
        self.assertFalse(result.ok)
        quartz.CGEventPost.assert_not_called()
        quartz.can_paste.return_value = True
        driver.target = None
        self.assertFalse(driver.paste_to_previous().ok)
        quartz.CGEventPost.assert_not_called()

    def test_macos_shortcut_write_and_pause_preserve_binding(self):
        """Writing, pausing and resuming keep the binding, and failed writes keep the old one."""
        from clipx.platforms.macos.shortcuts import MacOSGlobalShortcut
        native = Mock()
        native.register.return_value = object()
        with tempfile.TemporaryDirectory() as folder:
            backend = MacOSGlobalShortcut(Path(folder) / 'settings.json', native=native)
            backend.start(lambda: None)
            previous = backend.read()
            backend.write('Ctrl+Shift+L')
            self.assertEqual(backend.read(), 'Ctrl+Shift+L')
            paused = backend.pause()
            self.assertEqual(backend.read(), 'Ctrl+Shift+L')
            backend.resume(paused)
            native.register.side_effect = RuntimeError('em uso')
            with self.assertRaises(RuntimeError):
                backend.write('Ctrl+Shift+M')
            self.assertEqual(backend.read(), 'Ctrl+Shift+L')
            backend.stop()

    def test_macos_paste_waits_for_correct_target_and_times_out_without_keys(self):
        """Paste waits for the target app to come forward and times out without posting keys."""
        from clipx.platforms.macos.desktop import MacOSDesktopDriver
        appkit, quartz, target = Mock(), Mock(), Mock()
        quartz.can_paste.return_value = True
        target.isTerminated.return_value = False
        target.activateWithOptions_.return_value = True
        target.processIdentifier.return_value = 42
        appkit.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value.processIdentifier.return_value = 99
        driver = MacOSDesktopDriver(appkit=appkit, quartz=quartz, permissions=quartz)
        driver.target = target
        with patch('clipx.platforms.macos.desktop.time.monotonic', side_effect=[0, 2]):
            self.assertFalse(driver.paste_to_previous().ok)
        quartz.CGEventPost.assert_not_called()
        appkit.NSWorkspace.sharedWorkspace.return_value.frontmostApplication.return_value.processIdentifier.return_value = 42
        self.assertTrue(driver.paste_to_previous().ok)
        self.assertEqual(quartz.CGEventPost.call_count, 2)

    def test_macos_shortcut_save_failure_unregisters_new_and_keeps_old(self):
        """A persistence failure unregisters the new hot key and restores the previous handle."""
        from clipx.platforms.macos.shortcuts import MacOSGlobalShortcut
        native = Mock()
        old, new = object(), object()
        native.register.side_effect = [old, new]
        with tempfile.TemporaryDirectory() as folder:
            backend = MacOSGlobalShortcut(Path(folder) / 'settings.json', native=native)
            backend.start(lambda: None)
            value = backend.read()
            with patch.object(backend, '_persist', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    backend.write('Ctrl+Alt+L')
            self.assertIs(backend.handle, old)
            self.assertEqual(backend.read(), value)
            native.unregister.assert_called_once_with(new)
            backend.stop()

    def test_macos_empty_text_never_adds_history_and_read_errors_surface(self):
        """An unreadable pasteboard reports permission required and stores nothing."""
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver, TEXT_TYPE
        from clipx.platforms.base import Status
        board = Mock()
        board.changeCount.return_value = 1
        board.types.return_value = [TEXT_TYPE]
        board.stringForType_.return_value = None
        driver = MacOSClipboardDriver(pasteboard=board)
        sink = Mock()
        self.assertEqual(driver.poll(sink).status, Status.PERMISSION_REQUIRED)
        sink.save.assert_not_called()

    def test_linux_worker_selection_and_failures(self):
        """The Linux driver chooses an X11 or wl-paste worker and reports failed writes."""
        from clipx.platforms.linux.clipboard import LinuxClipboardDriver
        driver = LinuxClipboardDriver()
        with patch.dict(os.environ, {'DISPLAY': ':0'}):
            self.assertEqual(driver.listener_command(Path('test.db'))[-1], '--watch-x11')
        with patch.dict(os.environ, {'DISPLAY': ''}):
            self.assertEqual(driver.listener_command(Path('test.db'))[0], 'wl-paste')
        with patch('clipx.platforms.linux.clipboard.shutil.which', return_value=None):
            self.assertFalse(driver.write_text('failed').ok)

    def test_initial_hotkey_conflict_can_be_fixed_in_preferences(self):
        """A failing default hot key does not block later registration from preferences."""
        from clipx.platforms.macos.shortcuts import MacOSGlobalShortcut
        native = Mock()
        native.register.side_effect = [RuntimeError('default in use'), object()]
        with tempfile.TemporaryDirectory() as folder:
            backend = MacOSGlobalShortcut(Path(folder) / 'settings.json', native=native)
            with self.assertRaises(RuntimeError):
                backend.start(lambda: None)
            backend.write('Ctrl+Alt+L')
            self.assertEqual(backend.read(), 'Ctrl+Alt+L')
            self.assertIsNotNone(backend.handle)
            backend.stop()

    def test_linux_observation_stop_closes_listener(self):
        """Stopping observation from the listener closes it and reports success."""
        import threading
        from clipx.platforms.linux.clipboard import LinuxClipboardDriver
        driver = LinuxClipboardDriver()
        stopped = threading.Event()
        listener = Mock()
        listener.run.side_effect = lambda event: driver.stop_observation()
        report = Mock()
        with patch.dict(os.environ, {'DISPLAY': ':0'}), patch('clipx.platforms.linux.capture.X11ClipboardListener', return_value=listener):
            driver.start_observation(Mock(), stopped, report)
        self.assertTrue(stopped.is_set())
        listener.close.assert_called_once()
        self.assertTrue(report.call_args.args[0].ok)
