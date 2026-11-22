"""Regressions for GNOME startup completion, responsive copy and automatic paste."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import struct
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt6.QtCore import QThread, QThreadPool, QTimer
from PyQt6.QtWidgets import QApplication
from clipx.platforms.base import Result, Status
from clipx.platforms.linux.activation import finish_startup
from clipx.platforms.linux.clipboard import LinuxClipboardDriver
from clipx.platforms.linux.desktop import LinuxDesktopDriver, MANUAL_PASTE
from clipx.platforms.linux.paste import PasteKeyboard
from clipx.platforms.linux.processes import helper_environment
from clipx.services import ClipboardService
from clipx.storage import Storage

GNOME = {'XDG_SESSION_TYPE': 'wayland', 'XDG_CURRENT_DESKTOP': 'ubuntu:GNOME',
         'WAYLAND_DISPLAY': 'wayland-0', 'DISPLAY': ':0'}


class LinuxCopyTests(unittest.TestCase):
    """Test native command boundaries without a real clipboard or input device."""

    def test_helpers_drop_launch_tokens_but_keep_session_credentials(self):
        with patch.dict(os.environ, {**GNOME, 'DESKTOP_STARTUP_ID': 'startup',
                                     'XDG_ACTIVATION_TOKEN': 'native'}):
            env = helper_environment()
            self.assertNotIn('DESKTOP_STARTUP_ID', env)
            self.assertNotIn('XDG_ACTIVATION_TOKEN', env)
            self.assertEqual(env['DISPLAY'], ':0')
            self.assertEqual(os.environ['XDG_ACTIVATION_TOKEN'], 'native')

    def test_text_and_image_copy_do_not_inherit_desktop_startup(self):
        with patch.dict(os.environ, {'DESKTOP_STARTUP_ID': 'startup', 'XDG_ACTIVATION_TOKEN': 'native'}), \
             patch('shutil.which', return_value='/bin/tool'), \
             patch('clipx.platforms.linux.clipboard.subprocess.Popen') as popen, \
             patch('clipx.platforms.linux.clipboard.subprocess.run') as run:
            popen.return_value.returncode = 0
            run.return_value.returncode = 0
            driver = LinuxClipboardDriver()
            self.assertTrue(driver.write_text('text').ok)
            self.assertTrue(driver.write_image(b'png').ok)
            for call in (popen.call_args, run.call_args):
                self.assertNotIn('DESKTOP_STARTUP_ID', call.kwargs['env'])
                self.assertNotIn('XDG_ACTIVATION_TOKEN', call.kwargs['env'])

    def test_native_keyboard_reuses_device_and_sends_only_ctrl_v(self):
        keyboard = PasteKeyboard()
        with patch('clipx.platforms.linux.paste.os.open', return_value=42) as open_device, \
             patch('clipx.platforms.linux.paste.fcntl.ioctl') as ioctl, \
             patch('clipx.platforms.linux.paste.os.write', side_effect=lambda fd, data: len(data)) as write, \
             patch('clipx.platforms.linux.paste.os.close') as close, \
             patch('clipx.platforms.linux.paste.time.monotonic', side_effect=[0, 2, 3]):
            self.assertTrue(keyboard.paste(threading.Event()))
            self.assertTrue(keyboard.paste(threading.Event()))
            keyboard.close()
            keyboard.close()
        open_device.assert_called_once_with('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        self.assertIn((42, 0x40045565, 31), [call.args for call in ioctl.call_args_list])
        self.assertIn((42, 0x40045565, 47), [call.args for call in ioctl.call_args_list])
        self.assertEqual(ioctl.call_args.args, (42, 0x5502))
        close.assert_called_once_with(42)
        expected = [(1, 29, 1), (0, 0, 0), (1, 47, 1), (0, 0, 0),
                    (1, 47, 0), (0, 0, 0), (1, 29, 0), (0, 0, 0)]
        self.assertEqual(write.call_count, 2)
        for call in write.call_args_list:
            self.assertEqual([event[2:] for event in struct.iter_unpack('@llHHi', call.args[1])],
                             expected)

    def test_missing_or_inaccessible_uinput_reports_manual_paste(self):
        driver = LinuxDesktopDriver()
        for error in (FileNotFoundError('missing'), PermissionError('denied')):
            with self.subTest(error=error), patch('clipx.platforms.linux.paste.os.open', side_effect=error):
                result = driver.paste_to_previous()
            self.assertEqual((result.status, result.code, result.message),
                             (Status.UNAVAILABLE, 'paste_unavailable', MANUAL_PASTE))

    def test_cancelled_paste_never_opens_device(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch('clipx.platforms.linux.paste.os.open') as open_device:
            self.assertFalse(PasteKeyboard().paste(cancelled))
        open_device.assert_not_called()

    def test_cancelled_device_warmup_does_not_send_keys(self):
        cancelled = threading.Event()
        def cancel_during_registration(*args):
            cancelled.set()
        with patch('clipx.platforms.linux.paste.os.open', return_value=42), \
             patch('clipx.platforms.linux.paste.fcntl.ioctl', side_effect=cancel_during_registration), \
             patch('clipx.platforms.linux.paste.os.write') as write, \
             patch('clipx.platforms.linux.paste.os.close'):
            keyboard = PasteKeyboard()
            self.assertFalse(keyboard.paste(cancelled))
            keyboard.close()
        write.assert_not_called()

    def test_short_write_destroys_device_and_next_paste_can_retry(self):
        keyboard = PasteKeyboard()
        with patch('clipx.platforms.linux.paste.os.open', side_effect=[42, 43]), \
             patch('clipx.platforms.linux.paste.fcntl.ioctl') as ioctl, \
             patch('clipx.platforms.linux.paste.os.write', side_effect=lambda fd, data: 1 if fd == 42 else len(data)), \
             patch('clipx.platforms.linux.paste.os.close') as close, \
             patch('clipx.platforms.linux.paste.time.monotonic', side_effect=[0, 2, 3, 5]):
            self.assertFalse(keyboard.paste(threading.Event()))
            self.assertEqual(ioctl.call_args.args, (42, 0x5502))
            close.assert_called_once_with(42)
            self.assertTrue(keyboard.paste(threading.Event()))
            keyboard.close()

    def test_startup_completion_sends_remove_without_mapping_a_window(self):
        connection = Mock()
        root = connection.screen.return_value.root
        source = root.create_window.return_value
        source.id = 123
        connection.intern_atom.side_effect = lambda name: 11 if name.endswith('BEGIN') else 12
        xlib = types.ModuleType('Xlib')
        xlib.X = SimpleNamespace(InputOnly=2, CopyFromParent=0, PropertyChangeMask=1)
        xlib.display = SimpleNamespace(Display=Mock(return_value=connection))
        xlib.protocol = SimpleNamespace(event=SimpleNamespace(ClientMessage=lambda **kwargs: SimpleNamespace(**kwargs)))
        with patch.dict('sys.modules', {'Xlib': xlib}):
            finish_startup('clipx-123_é_TIME456')
        events = [call.args[0] for call in root.send_event.call_args_list]
        message = b''.join(event.data[1] for event in events).rstrip(b'\0').decode()
        self.assertEqual(message, 'remove: ID="clipx-123_é_TIME456"')
        self.assertTrue(all(len(event.data[1]) == 20 for event in events))
        self.assertEqual(events[0].client_type, 11)
        source.map.assert_not_called()
        source.destroy.assert_called_once()
        connection.close.assert_called_once()


class LinuxCopyQtTests(unittest.TestCase):
    """Test completion and cancellation across workers, timers and IPC."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.storage = Storage(self.root / 'history.db')
        self.storage.add_clip('example text')
        self.driver = LinuxDesktopDriver()

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while not condition() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.005)
        self.assertTrue(condition())

    def window(self):
        from clipx.platforms.effects import OpaqueWindowEffects
        from clipx.shortcuts import ShortcutSettings
        from clipx.ui.pages.clipboard import ClipXMainWindow
        platform = SimpleNamespace(name='linux', desktop=self.driver, clipboard=LinuxClipboardDriver(), effects=OpaqueWindowEffects())
        window = ClipXMainWindow(self.storage, ShortcutSettings(self.root / 'settings.json'), platform)
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_slow_text_copy_keeps_qt_responsive_and_delivers_once_on_gui_thread(self):
        service = ClipboardService(self.storage, LinuxClipboardDriver())
        started, release = threading.Event(), threading.Event()
        replies, ticks = [], []
        def slow_write(text):
            started.set()
            release.wait(3)
            return Result()
        try:
            with patch.object(service.driver, 'write_text', side_effect=slow_write) as write:
                service.copy_async(self.storage.get_clips()[0], lambda result: replies.append((result, QThread.currentThread())))
                self.assertTrue(started.wait(1))
                QTimer.singleShot(0, lambda: ticks.append(True))
                self.wait_for(lambda: bool(ticks))
                rejected = []
                service.copy_async(self.storage.get_clips()[0], rejected.append)
                self.assertFalse(rejected[0].ok)
                self.assertEqual(replies, [])
                release.set()
                self.wait_for(lambda: bool(replies))
                self.assertTrue(replies[0][0].ok)
                self.assertEqual(replies[0][1], self.app.thread())
                write.assert_called_once()
        finally:
            release.set()
            QThreadPool.globalInstance().waitForDone(5000)
            self.app.processEvents()

    def test_paste_result_survives_worker_exit_and_runs_on_gui_thread(self):
        replies = []
        with patch.object(self.driver._paste_keyboard, 'paste', return_value=False):
            self.driver.paste_to_previous(lambda result: replies.append((result, QThread.currentThread())))
            self.wait_for(lambda: bool(replies))
        self.assertEqual(replies[0][0].message, MANUAL_PASTE)
        self.assertEqual(replies[0][1], self.app.thread())

    def test_generated_startup_is_finished_after_show_and_not_reused(self):
        window = Mock()
        window.isVisible.return_value = False
        env = {**GNOME, 'XDG_ACTIVATION_TOKEN': '', 'DESKTOP_STARTUP_ID': '', 'QT_QPA_PLATFORM': 'wayland'}
        with patch.dict(os.environ, env), patch('PyQt6.QtWidgets.QApplication.platformName', return_value='wayland'), \
             patch('clipx.platforms.linux.activation.x11_startup_token', return_value='generated'), \
             patch('clipx.platforms.linux.activation.finish_startup') as finish:
            self.driver.open_search(window)
            finish.assert_not_called()
            self.app.processEvents()
            finish.assert_called_once_with('generated')
            self.assertEqual(self.driver.startup_id, '')
            self.assertNotIn('XDG_ACTIVATION_TOKEN', os.environ)
            self.driver.stop()
            finish.assert_called_once()

    def test_native_wayland_token_is_not_finished_as_x11_announcement(self):
        with patch.dict(os.environ, {'XDG_ACTIVATION_TOKEN': 'clipx-native-token', 'DESKTOP_STARTUP_ID': ''}), \
             patch('clipx.platforms.linux.activation.finish_startup') as finish:
            token = self.driver.activation_token()
            self.assertEqual(self.driver.startup_id, '')
            self.driver.open_search(Mock(), token)
            self.app.processEvents()
        finish.assert_not_called()

    def test_native_focus_and_desktop_startup_ids_remain_separate(self):
        with patch.dict(os.environ, {'XDG_ACTIVATION_TOKEN': 'native-focus', 'DESKTOP_STARTUP_ID': 'desktop-launch'}), \
             patch('clipx.platforms.linux.activation.finish_startup') as finish:
            token = self.driver.activation_token()
            self.assertEqual((token, self.driver.startup_id), ('native-focus', 'desktop-launch'))
            self.driver.open_search(Mock(), token)
            self.app.processEvents()
            finish.assert_called_once_with('desktop-launch')
            self.assertNotIn('DESKTOP_STARTUP_ID', os.environ)

    def test_failed_show_and_cancelled_show_finish_startup_once(self):
        with patch('clipx.platforms.linux.activation.finish_startup') as finish:
            window = Mock()
            window.showNormal.side_effect = RuntimeError('show failed')
            with self.assertRaises(RuntimeError):
                self.driver.open_search(window, 'token', startup_id='failed')
            finish.assert_called_once_with('failed')
            finish.reset_mock()
            self.driver.open_search(Mock(), 'token', startup_id='cancelled')
            self.driver.stop()
            self.app.processEvents()
            finish.assert_called_once_with('cancelled')

    def test_setup_failure_completes_pending_startup(self):
        from clipx.main import run_gui
        platform = SimpleNamespace(name='linux', paths=Mock(), desktop=self.driver)
        def activation():
            self.driver.startup_id = 'setup-failed'
            return 'focus-token'
        with patch('clipx.platforms.get_platform', return_value=platform), \
             patch.object(self.driver, 'activation_token', side_effect=activation), \
             patch('PyQt6.QtWidgets.QApplication', return_value=self.app), \
             patch('clipx.instance.DesktopInstance', side_effect=RuntimeError('socket unavailable')), \
             patch('clipx.platforms.linux.activation.finish_startup') as finish:
            with self.assertRaises(RuntimeError):
                run_gui()
        finish.assert_called_once_with('setup-failed')

    def test_hidden_secondary_launch_finishes_its_own_startup(self):
        from clipx.main import run_gui
        platform = SimpleNamespace(name='linux', paths=Mock(), desktop=self.driver)
        def activation():
            self.driver.startup_id = 'hidden-launch'
            return 'focus-token'
        instance = Mock()
        instance.acquire.return_value = False
        with patch.dict(os.environ, {'DESKTOP_STARTUP_ID': 'hidden-launch'}), \
             patch('clipx.platforms.get_platform', return_value=platform), \
             patch.object(self.driver, 'activation_token', side_effect=activation), \
             patch('PyQt6.QtWidgets.QApplication', return_value=self.app), \
             patch('clipx.instance.DesktopInstance', return_value=instance), \
             patch('clipx.platforms.linux.activation.finish_startup') as finish:
            run_gui(start_hidden=True)
        finish.assert_called_once_with('hidden-launch')
        instance.acquire.assert_called_once_with(show=False, activation_token='focus-token', startup_id='hidden-launch')

    def test_ipc_forwards_startup_id_independently_of_focus_token(self):
        from clipx.instance import DesktopInstance
        # Unix socket paths are short on macOS; isolate the runtime under /tmp.
        runtime = tempfile.TemporaryDirectory(dir='/tmp')
        self.addCleanup(runtime.cleanup)
        primary = DesktopInstance(runtime=runtime.name)
        self.addCleanup(primary.close)
        self.assertTrue(primary.acquire())
        received = []
        primary.listen(lambda **kwargs: received.append(kwargs))
        secondary = DesktopInstance(runtime=runtime.name)
        self.assertFalse(secondary.acquire(activation_token='native-focus', startup_id='announcement'))
        self.wait_for(lambda: bool(received))
        self.assertEqual(received, [{'activation_token': 'native-focus', 'startup_id': 'announcement'}])

    def test_linux_paste_waits_for_hidden_and_inactive_search(self):
        window = self.window()
        window._paste_generation = 1
        with patch.object(window, 'isVisible', return_value=False), \
             patch.object(window, 'isActiveWindow', side_effect=[True, False]), \
             patch.object(window, '_paste') as paste:
            window._wait_for_paste(1, time.monotonic() + 1)
            paste.assert_not_called()
            self.wait_for(lambda: paste.called)
        paste.assert_called_once()

    def test_reopening_search_cancels_scheduled_paste(self):
        window = self.window()
        window._paste_generation = 2
        with patch.object(window, '_paste') as paste:
            window._wait_for_paste(1, time.monotonic() + 1)
        paste.assert_not_called()
        self.assertEqual(window._operation_message,
                         'Conteúdo copiado. Colagem cancelada porque a pesquisa foi reaberta; use Ctrl+V.')

    def test_focus_timeout_preserves_clipboard_and_does_not_paste(self):
        window = self.window()
        with patch.object(window, 'isVisible', return_value=False), \
             patch.object(window, 'isActiveWindow', return_value=True), patch.object(window, '_paste') as paste:
            window._wait_for_paste(0, time.monotonic() - 1)
        paste.assert_not_called()
        self.assertEqual(window._operation_message, MANUAL_PASTE)

    def test_copy_failure_keeps_search_and_recency_and_never_schedules_paste(self):
        window = self.window()
        window.show()
        before = self.storage.get_clips()[0].updated_at
        with patch.object(window.platform.clipboard, 'write_text', return_value=Result(Status.ERROR, 'failed')), \
             patch.object(window, '_wait_for_paste') as paste:
            window._copy_selected(paste=True)
            self.wait_for(lambda: not window._copy_busy)
        self.assertTrue(window.isVisible())
        self.assertEqual(self.storage.get_clips()[0].updated_at, before)
        paste.assert_not_called()

    def test_copy_only_never_schedules_automatic_paste(self):
        window = self.window()
        window.show()
        with patch.object(window.platform.clipboard, 'write_text', return_value=Result()), \
             patch.object(window, '_wait_for_paste') as paste:
            window._copy_selected(paste=False)
            self.wait_for(lambda: not window._copy_busy)
        self.assertFalse(window.isVisible())
        paste.assert_not_called()
