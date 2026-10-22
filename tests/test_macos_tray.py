"""Regression: menu tracking is not a mouse click on macOS 27."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from clipx.storage import Storage
from clipx.shortcuts import ShortcutSettings
from clipx.platforms import get_platform
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.controllers.tray import ClipXTray


class MacOSTrayTests(unittest.TestCase):
    """Verify tray activation behavior while a menu is being tracked."""

    @classmethod
    def setUpClass(cls):
        """Create the shared QApplication without quitting on the last closed window."""
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def test_menu_activation_does_not_open_search_while_menu_is_tracking(self):
        """A tray trigger is ignored while the menu tracks; the Open action still opens search."""
        with tempfile.TemporaryDirectory() as folder:
            window = ClipXMainWindow(Storage(Path(folder) / 'history.db'),
                ShortcutSettings(Path(folder) / 'settings.json'), get_platform('linux'))
            tray = ClipXTray(window.storage, window)
            tray.platform = SimpleNamespace(name='macos')
            try:
                with patch.object(tray, 'open_search') as show:
                    tray._on_activated(QSystemTrayIcon.ActivationReason.Trigger)
                    show.assert_not_called()
                    tray.open_action.trigger()
                    show.assert_called_once()
            finally:
                tray.refresh_timer.stop()
                tray.deleteLater()
                window.close()
                window.deleteLater()
