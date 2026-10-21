"""Behavior of the redesigned preferences, independent of the native desktop."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QKeySequence
from clipx.shortcuts import SHORTCUTS, ShortcutSettings
from clipx.storage import Storage
from clipx.platforms import get_platform
from clipx.platforms.linux.shortcuts import from_gnome, to_gnome
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.pages.shortcuts import ShortcutsDialog


class ShortcutPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        self.settings = ShortcutSettings(folder / 'settings.json')
        self.window = ClipXMainWindow(Storage(folder / 'history.db'), self.settings, get_platform('linux'))
        self.backend = Mock()
        self.backend.read.return_value = '<Super>v'
        self.backend.from_binding.side_effect = from_gnome
        self.backend.to_binding.side_effect = to_gnome
        self.backend.default_sequence = 'Meta+V'
        self.backend.modifier_hint = 'Super = tecla Windows'
        self.backend.pause.return_value = '<Super>v'
        self.backend.conflicts.return_value = []
        self.page = ShortcutsDialog(self.window, self.backend)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.page.close)

    def test_sidebar_counts_real_actions_and_filters_without_recreating_editors(self):
        self.assertEqual(self.page.sidebar.counts['all'], len(SHORTCUTS) + 1)
        recorder = self.page.editors['pin']
        self.page.sidebar.buttons['system'].click()
        self.assertEqual(self.page.sections.visible_names(), ['global'])
        self.page.sidebar.buttons['filters'].click()
        self.assertEqual(self.page.sections.visible_names(), ['filter'])
        self.page.sidebar.buttons['all'].click()
        self.assertIs(self.page.editors['pin'], recorder)

    def test_search_matches_titles_and_keystrokes_and_has_empty_state(self):
        self.page.search_field.input.setText('fixar')
        self.assertEqual(self.page.sections.visible_names(), ['pin'])
        self.page.search_field.input.setText('Ctrl+P')
        self.assertEqual(self.page.sections.visible_names(), ['pin'])
        self.page.search_field.input.setText('nonexistent')
        self.assertEqual(self.page.sections.visible_names(), [])
        self.assertFalse(self.page.sections.empty_label.isHidden())
        self.page.search_field.input.clear()
        self.assertEqual(len(self.page.sections.visible_names()), len(SHORTCUTS) + 1)

    def test_dirty_count_tracks_draft_revert_and_cancel_does_not_persist(self):
        self.assertEqual(self.page.controller.pending_count, 0)
        self.assertFalse(self.page.apply_button.isEnabled())
        self.page.editors['pin'].setKeySequence(QKeySequence('Ctrl+L'))
        self.assertEqual(self.page.controller.pending_count, 1)
        self.assertIn('1 alteração', self.page.footer.change_label.text())
        self.assertTrue(self.page.rows['pin'].property('modified'))
        self.page.editors['pin'].setKeySequence(QKeySequence('Ctrl+P'))
        self.assertEqual(self.page.controller.pending_count, 0)
        self.page.editors['pin'].clear()
        self.page.reject()
        self.assertFalse(self.settings.path.exists())
        self.backend.write.assert_not_called()

    def test_switching_category_ends_recording_and_restores_global_binding(self):
        self.page.show()
        self.app.processEvents()
        self.page.controller.start_recording('global')
        self.page.sidebar.buttons['search'].click()
        self.assertIsNone(self.page.controller.recording_name)
        self.assertFalse(self.page.global_edit.recording)
        self.backend.resume.assert_called_once_with('<Super>v')

    def test_apply_saves_hidden_draft_from_another_category(self):
        self.page.editors['pin'].setKeySequence(QKeySequence('Ctrl+L'))
        self.page.sidebar.buttons['system'].click()
        self.page.apply_button.click()
        self.assertEqual(self.settings.load()['pin'], 'Ctrl+L')
        self.assertEqual(self.window.shortcuts['pin'], 'Ctrl+L')

    def test_recorder_exposes_keycaps_without_changing_serialization(self):
        recorder = self.page.editors['pin']
        self.assertEqual(recorder.keySequence().toString(), 'Ctrl+P')
        self.assertEqual(len(recorder.keycaps.caps), 2)
        self.assertEqual(recorder.keycaps.caps[-1].text(), 'P')

    def test_find_shortcut_focuses_search_and_does_not_steal_recorded_combination(self):
        from PyQt6.QtCore import Qt
        from PyQt6.QtTest import QTest
        self.page.show()
        self.page.activateWindow()
        self.app.processEvents()
        QTest.keyClick(self.page, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertTrue(self.page.search_field.input.hasFocus())
        self.page.controller.start_recording('pin')
        QTest.keyClick(self.page.editors['pin'], Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
        self.assertEqual(self.page.editors['pin'].keySequence().toString(), 'Ctrl+F')
        self.assertFalse(self.page.editors['pin'].recording)

    def test_restore_defaults_only_changes_draft(self):
        self.page.editors['pin'].clear()
        self.assertEqual(self.page.controller.pending_count, 1)
        self.page.footer.reset.click()
        self.assertEqual(self.page.controller.pending_count, 0)
        self.assertEqual(self.page.editors['pin'].keySequence().toString(), 'Ctrl+P')
        self.assertFalse(self.settings.path.exists())
        self.backend.write.assert_not_called()

    def test_preferences_and_picker_use_system_window_controls(self):
        from PyQt6.QtCore import Qt
        from clipx.ui.pages.shortcut_picker import ShortcutPicker
        self.assertFalse(self.page.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertEqual(self.page.windowModality(), Qt.WindowModality.NonModal)
        self.assertFalse(self.page.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.page.show()
        picker = ShortcutPicker('Ctrl+L', self.page)
        try:
            self.assertFalse(picker.windowFlags() & Qt.WindowType.FramelessWindowHint)
            picker.show()
            picker.close()
            self.assertFalse(picker.isVisible())
        finally:
            picker.deleteLater()
        self.page.editors['pin'].clear()
        self.page.close()
        self.assertFalse(self.page.isVisible())
        self.assertFalse(self.settings.path.exists())
