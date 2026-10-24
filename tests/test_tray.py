"""Tray menu, instance routing and activation-token behavior."""
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_QPA_PLATFORMTHEME"] = "generic"

from PyQt6.QtCore import QCoreApplication, QEventLoop, QTimer, Qt
from PyQt6.QtNetwork import QLocalSocket
from PyQt6.QtWidgets import QApplication

from clipx.instance import DesktopInstance
from clipx.platforms import get_platform
from clipx.storage import Storage
from clipx.shortcuts import ShortcutSettings
from clipx.ui.controllers.tray import ClipXTray
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.utils import format_relative_time


class TrayTests(unittest.TestCase):
    """Exercise tray menus, single-instance routing and foreground activation."""

    @classmethod
    def setUpClass(cls):
        """Create the shared offscreen QApplication."""
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        """Build isolated storage, window and tray fixtures."""
        self.temp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.storage = Storage(Path(self.temp.name) / "history.db")
        self.window = ClipXMainWindow(self.storage, ShortcutSettings(Path(self.temp.name) / "settings.json"), platform=get_platform("linux"))
        self.tray = ClipXTray(self.storage, self.window)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.tray.deleteLater)
        self.addCleanup(self.tray.refresh_timer.stop)

    def populate(self):
        """Store seven clips with increasing timestamps, pin one and refresh the menu."""
        for n in range(7):
            clip_id = self.storage.add_clip(f"clip {n}")
            with self.storage._get_connection() as conn:
                conn.execute(
                    "UPDATE clips SET updated_at = ? WHERE id = ?",
                    (f"2026-01-01 00:00:0{n}", clip_id),
                )
        self.storage.toggle_pin(1)
        self.tray.refresh_menu()

    def wait_for(self, condition, timeout_ms=5000):
        """Process Qt events until the condition holds or the timeout expires.

        QLocalServer signal delivery depends on the event loop and has no deterministic
        deadline; on slow runners a short fixed wait may end before the server dispatches
        readyRead/newConnection.

        Args:
            condition: Callable returning truthy once the awaited state is reached.
            timeout_ms: Maximum time to wait, in milliseconds.

        Raises:
            AssertionError: If the condition is still false after the timeout.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        while not condition():
            if time.monotonic() > deadline:
                self.fail(f"Condição não atendida em {timeout_ms} ms")
            QCoreApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)

    def test_recent_five_ignore_pin_priority_and_refresh(self):
        """The menu lists the five most recent clips, refreshes and shows an empty state."""
        self.populate()
        self.assertEqual(
            [a.text() for a in self.tray.menu.actions() if not a.isSeparator() and a.isVisible()],
            ["Pesquisa", "Open", "Últimos 5 clips", "clip 6", "clip 5", "clip 4", "clip 3",
             "clip 2", "Configurações", "Preferências…", "Atalhos", "Captura ativa", "Aplicativo", "Verificar atualizações…", "Quit"],
        )
        self.assertEqual(self.storage.get_clips()[0].content, "clip 0")
        self.storage.add_clip("clip 0")
        self.tray.refresh_menu()
        self.assertEqual(self.tray.clip_actions[0].text(), "clip 0")
        self.storage.clear_history(keep_pinned=False)
        self.tray.refresh_menu()
        empty = self.tray.empty_action
        self.assertEqual(empty.text(), "Histórico vazio")
        self.assertFalse(empty.isEnabled())

    def test_preview_copies_full_content_and_updates_recency(self):
        """Menu labels escape and truncate previews while triggering copies the full text."""
        content = "a & b\n" + "long text " * 20
        self.storage.add_clip(content)
        self.tray.refresh_menu()
        action = self.tray.clip_actions[0]
        self.assertIn("&&", action.text())
        self.assertTrue(action.text().endswith("…"))
        self.assertNotIn("\n", action.text())
        from clipx.platforms.base import Result
        with patch.object(self.window.platform.clipboard, "write_text", return_value=Result()) as copy:
            action.trigger()
            copy.assert_called_once_with(content)
        self.assertEqual(self.tray.clip_actions[0].data().content, content)

    def test_update_action_opens_preferences_and_reuses_shared_service(self):
        """The explicit tray action checks; ordinary navigation does not."""
        dialog = Mock()
        with patch.object(self.tray, 'open_preferences') as open_preferences, patch.object(self.tray.updates, 'check') as check:
            self.tray.menu.updates_action.trigger()
            open_preferences.assert_called_once_with('updates')
            check.assert_called_once_with()
        self.tray.shortcuts_dialog = dialog
        with patch.object(self.tray, 'open_preferences'), patch.object(self.tray.updates, 'launch_install') as launch, patch.object(self.tray.updates, 'defer_install') as defer:
            dialog.prepare_update_restart.return_value = False
            self.tray._install_update()
            launch.assert_not_called()
            defer.assert_called_once_with()
            dialog.prepare_update_restart.return_value = True
            self.tray._install_update()
            launch.assert_called_once_with()
        self.tray.shortcuts_dialog = None

    def test_open_close_reopen_and_quit(self):
        """Open shows the search, closing keeps the app alive, and quit emits aboutToQuit."""
        self.tray.open_action.trigger()
        self.assertTrue(self.window.isVisible())
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.app.quitOnLastWindowClosed())
        self.storage.add_clip("new clip while hidden")
        self.tray.open_search()
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.window.clip_list.count(), 1)
        self.window.close()
        quit_events = []
        callback = lambda: quit_events.append(True)
        self.app.aboutToQuit.connect(callback)
        try:
            QTimer.singleShot(0, self.tray.quit_action.trigger)
            self.app.exec()
            self.assertEqual(quit_events, [True])
        finally:
            self.app.aboutToQuit.disconnect(callback)

    def test_menu_keeps_actions_and_click_targets_stable_while_open(self):
        """An open menu keeps its actions and targets fixed until it is hidden."""
        self.populate()
        actions = self.tray.menu.actions()
        self.tray._about_to_show()
        self.storage.add_clip("new clipboard content")
        self.tray.refresh_menu()
        self.assertEqual(self.tray.clip_actions[0].text(), "clip 6")
        self.tray._about_to_hide()
        self.tray.refresh_menu()
        self.assertEqual(self.tray.clip_actions[0].text(), "new clipboard content")
        self.assertEqual(self.tray.menu.actions(), actions)

    def test_shortcuts_menu_opens_one_dialog_and_cancel_does_not_save(self):
        """The shortcuts action reuses one dialog and cancelling persists no binding."""
        with patch("clipx.ui.pages.shortcuts.GlobalShortcut") as backend:
            from clipx.platforms.linux.shortcuts import from_gnome, to_gnome
            backend.return_value.read.return_value = "<Super>v"
            backend.return_value.from_binding.side_effect = from_gnome
            backend.return_value.to_binding.side_effect = to_gnome
            backend.return_value.modifier_hint = "Super = tecla Windows"
            backend.return_value.default_sequence = "Meta+V"
            self.tray.shortcuts_action.trigger()
            dialog = self.tray.shortcuts_dialog
            self.assertTrue(dialog.isVisible())
            self.tray.shortcuts_action.trigger()
            self.assertIs(self.tray.shortcuts_dialog, dialog)
            self.tray.open_search()
            self.assertFalse(self.window.isVisible())
            self.assertTrue(dialog.isVisible())
            dialog.reject()
            self.assertIsNone(self.tray.shortcuts_dialog)
            backend.return_value.write.assert_not_called()
            self.assertFalse(self.window.shortcut_settings.path.exists())

    def test_instance_routes_show_and_releases_lock(self):
        """A secondary instance forwards show to the primary and can acquire after release."""
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name}):
            instance = DesktopInstance(runtime=self.temp.name)
            self.assertTrue(instance.acquire())
            self.addCleanup(instance.close)
            opened = []
            instance.listen(lambda: opened.append(True))
            secondary = DesktopInstance(runtime=self.temp.name)
            self.assertFalse(secondary.acquire(show=False))
            socket = QLocalSocket()
            socket.connectToServer(instance.name)
            self.assertTrue(socket.waitForConnected(500))
            socket.write(b"show\n")
            socket.flush()
            self.wait_for(lambda: opened)
            self.assertEqual(opened, [True])
            socket.close()
            instance.close()
            self.assertTrue(secondary.acquire())
            secondary.close()

    def test_shortcut_process_forwards_its_activation_token_to_the_tray(self):
        """A secondary launch forwards its activation token to the primary listener."""
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.temp.name}):
            primary = DesktopInstance(runtime=self.temp.name)
            self.assertTrue(primary.acquire())
            self.addCleanup(primary.close)
            received = []
            primary.listen(lambda activation_token="": received.append(activation_token))
            secondary = DesktopInstance(runtime=self.temp.name)
            self.assertFalse(secondary.acquire(activation_token="gnome-token"))
            self.wait_for(lambda: received)
            self.assertEqual(received, ["gnome-token"])

    def test_foreground_request_uses_the_token_for_the_correct_window(self):
        """Bringing a window forward consumes the token and activates only visible windows."""
        for was_visible in (False, True):
            window = Mock()
            window.isVisible.return_value = was_visible
            captured = []
            window.showNormal.side_effect = lambda: captured.append(os.environ.get("XDG_ACTIVATION_TOKEN"))
            with patch("clipx.platforms.linux.desktop.QApplication.platformName", return_value="wayland"):
                self.tray._bring_to_front(window, "foreground-token")
            self.assertEqual(captured, ["foreground-token"])
            window.raise_.assert_called_once()
            if was_visible:
                window.activateWindow.assert_called_once()
            else:
                window.activateWindow.assert_not_called()  # Qt activates while mapping the surface.
            self.assertNotIn("XDG_ACTIVATION_TOKEN", os.environ)
        self.assertTrue(self.window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)

    def test_relative_time_accepts_fractional_timestamps(self):
        """A fractional-second UTC timestamp is recognized as the current time."""
        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")
        self.assertEqual(format_relative_time(timestamp), "agora")


if __name__ == "__main__":
    unittest.main()
