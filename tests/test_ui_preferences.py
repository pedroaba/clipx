"""Persistence and live preferences using isolated storage and fake native shortcuts."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QKeySequence
from clipx.preferences import UISettings, DEFAULT_UI, validate_ui
from clipx.shortcuts import ShortcutSettings
from clipx.storage import Storage
from clipx.platforms.effects import OpaqueWindowEffects
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.pages.preferences import PreferencesDialog


class UISettingsTests(unittest.TestCase):
    def test_invalid_values_fall_back_individually(self):
        values = validate_ui({'theme': 'light', 'scale': True, 'lines': 99, 'metadata': 1})
        self.assertEqual(values['theme'], 'light')
        self.assertEqual(values['scale'], 100)
        self.assertEqual(values['lines'], 2)
        self.assertIs(values['metadata'], True)

    def test_atomic_save_preserves_unrelated_fields_and_shortcuts(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'settings.json'
            shortcuts = ShortcutSettings(path)
            shortcuts.save(shortcuts.load())
            data = json.loads(path.read_text())
            data['future'] = {'value': 7}
            path.write_text(json.dumps(data))
            settings = UISettings(path)
            settings.save({**DEFAULT_UI, 'theme': 'light'})
            shortcuts.save(shortcuts.load())
            saved = json.loads(path.read_text())
            self.assertEqual(saved['future'], {'value': 7})
            self.assertEqual(settings.load()['theme'], 'light')
            before = path.read_text()
            with patch('pathlib.Path.replace', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    settings.save(DEFAULT_UI)
            self.assertEqual(path.read_text(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])


class PreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)
        self.platform = SimpleNamespace(name='test', effects=OpaqueWindowEffects(), clipboard=Mock(), desktop=Mock())
        self.window = ClipXMainWindow(Storage(path / 'history.db'), ShortcutSettings(path / 'settings.json'), self.platform)
        self.window.storage.add_clip('First line\nSecond line\nThird line', 'code', 'python')
        self.window.load_clips()
        self.backend = Mock()
        self.backend.read.return_value = 'Meta+V'
        self.backend.from_binding.side_effect = lambda value: value
        self.backend.to_binding.side_effect = lambda value: value
        self.backend.default_sequence = 'Meta+V'
        self.backend.modifier_hint = 'Super'
        self.backend.conflicts.return_value = []
        self.page = PreferencesDialog(self.window, self.backend)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.page.deleteLater)
        self.addCleanup(self.page.cancel_changes)

    def choose(self, key, value):
        self.page.controls[key].setCurrentIndex(self.page.controls[key].findData(value))

    def test_draft_survives_navigation_and_apply_keeps_dialog_open(self):
        self.page.show()
        self.choose('theme', 'light')
        self.page.select_section('content')
        self.choose('preview', False)
        self.page.select_section('appearance')
        self.assertEqual(self.page.ui_draft()['theme'], 'light')
        self.assertEqual(self.window.preferences['theme'], 'dark')
        self.page.apply_changes()
        self.assertTrue(self.page.isVisible())
        self.assertEqual(self.window.preferences['theme'], 'light')
        self.assertTrue(self.window.preview_pane.isHidden())
        self.assertFalse(self.page.dirty())
        self.assertFalse(self.page.apply_button.isEnabled())
        self.assertEqual(self.window.ui_settings.load()['theme'], 'light')
        self.assertEqual(self.page.footer.change_label.text(), 'Configurações aplicadas')

    def test_failure_preserves_live_state_and_draft_and_rolls_back_global(self):
        self.choose('theme', 'light')
        self.page.global_edit.setKeySequence(QKeySequence('Meta+L'))
        with patch.object(self.window.ui_settings, 'save', side_effect=OSError('disk full')):
            self.page.apply_changes()
        self.assertEqual(self.window.preferences['theme'], 'dark')
        self.assertEqual(self.page.ui_draft()['theme'], 'light')
        self.assertTrue(self.page.dirty())
        self.backend.write.assert_any_call('Meta+V')
        self.assertIn('disk full', self.page.general_error.text())

    def test_apply_shows_loading_during_save_and_restores_buttons(self):
        self.choose('theme', 'light')
        save = self.window.ui_settings.save

        def saving(*args, **kwargs):
            self.assertTrue(self.page.buttons.loading)
            self.assertEqual(self.page.apply_button.text(), 'Aplicando…')
            self.assertFalse(self.page.apply_button.icon().isNull())
            self.assertFalse(self.page.apply_button.isEnabled())
            self.assertFalse(self.page.buttons.cancel.isEnabled())
            self.assertTrue(self.page.buttons._spinner.isActive())
            save(*args, **kwargs)

        with patch.object(self.window.ui_settings, 'save', side_effect=saving):
            self.page.apply_changes()
        self.assertFalse(self.page.buttons.loading)
        self.assertFalse(self.page.buttons._spinner.isActive())
        self.assertEqual(self.page.apply_button.text(), 'Aplicar')
        self.assertTrue(self.page.apply_button.icon().isNull())
        self.assertTrue(self.page.buttons.cancel.isEnabled())
        self.assertFalse(self.page.apply_button.isEnabled())

        self.choose('theme', 'dark')
        with patch.object(self.window.ui_settings, 'save', side_effect=OSError('disk full')):
            self.page.apply_changes()
        self.assertFalse(self.page.buttons.loading)
        self.assertTrue(self.page.apply_button.isEnabled())
        self.assertTrue(self.page.buttons.cancel.isEnabled())
        self.assertFalse(self.page.general_error.isHidden())

    def test_restore_is_scoped_and_cancel_discards(self):
        self.choose('theme', 'light')
        self.choose('lines', 3)
        self.page.select_section('content')
        self.page.restore_section()
        self.assertEqual(self.page.ui_draft()['lines'], 2)
        self.assertEqual(self.page.ui_draft()['theme'], 'light')
        self.page.cancel_changes()
        self.assertEqual(self.window.preferences['theme'], 'dark')
        self.assertFalse(self.window.ui_settings.path.exists())

    def test_shortcuts_and_ui_apply_atomically_without_closing(self):
        self.page.show()
        self.choose('scale', 125)
        self.page.editors['pin'].setKeySequence(QKeySequence('Ctrl+L'))
        self.page.apply_changes()
        saved = json.loads(self.window.ui_settings.path.read_text())
        self.assertEqual(saved['ui']['scale'], 125)
        self.assertEqual(saved['shortcuts']['pin'], 'Ctrl+L')
        self.assertEqual(self.window.shortcuts['pin'], 'Ctrl+L')
        self.assertFalse(self.page.dirty())
        self.assertTrue(self.page.isVisible())

    def test_apply_clears_shortcut_pending_state_and_tracks_next_edit(self):
        self.page.controller.record_sequence('pin', 'Ctrl+L')
        self.assertEqual(self.page.controller.pending_count, 1)
        self.page.apply_changes()
        self.assertEqual(self.page.controller.pending_count, 0)
        self.assertTrue(self.page.rows['pin'].changed_dot.isHidden())
        self.assertEqual(self.page.messages['pin'].text(), '')
        self.assertEqual(self.page.footer.change_label.text(), 'Configurações aplicadas')
        self.assertFalse(self.page.apply_button.isEnabled())
        self.page.select_section('shortcuts')
        self.assertNotIn('não salva', self.page.footer.change_label.text())
        self.page.controller.clear_shortcut('pin')
        self.assertEqual(self.page.footer.change_label.text(), '1 alteração não salva')
        self.assertTrue(self.page.apply_button.isEnabled())

    def test_reopen_clear_resets_filter_and_selection(self):
        self.window.preferences['reopen'] = 'clear'
        self.window.search_bar.input_field.setText('missing')
        self.window.search_bar.filter_select.setCurrentIndex(1)
        self.window.prepare_open()
        self.assertEqual(self.window.current_query, '')
        self.assertEqual(self.window.current_filter, 'all')
        self.assertEqual(self.window.clip_list.currentRow(), 0)

    def test_geometry_restores_and_offscreen_position_is_clamped(self):
        self.window.preferences['position'] = 'last'
        self.window._saved_window = {'position': [90000, 90000], 'size': [800, 500], 'splitter': [300, 500]}
        self.window.restore_window()
        self.assertTrue(any(screen.availableGeometry().contains(self.window.frameGeometry().center()) for screen in self.app.screens()))
        self.assertEqual(self.window.width(), 800)

    def test_scale_is_not_cumulative_and_content_options_update(self):
        values = {**DEFAULT_UI, 'scale': 150, 'lines': 3, 'syntax': False, 'metadata': False}
        self.window.apply_preferences(values)
        margins = self.window.surface.layout().contentsMargins().left()
        self.window.apply_preferences(values)
        self.assertEqual(self.window.surface.layout().contentsMargins().left(), margins)
        item = self.window.clip_list.itemWidget(self.window.clip_list.item(0))
        self.window.show()
        self.app.processEvents()
        self.assertIn('Third line', item.subtitle.text())
        self.assertEqual(self.window.preview_pane.text_browser.toPlainText(), 'First line\nSecond line\nThird line')
        self.window.close()

    def test_recording_restores_pending_ui_count_when_stopped(self):
        self.choose('theme', 'light')
        self.page.controller.start_recording('pin')
        self.assertFalse(self.page.apply_button.isEnabled())
        self.page.controller.stop_recording()
        self.assertTrue(self.page.apply_button.isEnabled())
        self.assertIn('1 alteração', self.page.footer.change_label.text())

    def test_close_prompts_allow_continue_discard_and_apply(self):
        self.page.show()
        self.choose('theme', 'light')
        with patch.object(QMessageBox, 'exec'), patch.object(QMessageBox, 'clickedButton', return_value=None):
            self.page.reject()
        self.assertTrue(self.page.isVisible())
        self.assertTrue(self.page.dirty())
        def discard(box):
            for button in box.buttons():
                if button.text() == 'Descartar':
                    button.click()
        with patch.object(QMessageBox, 'exec', discard):
            self.page.reject()
        self.assertFalse(self.page.isVisible())
        self.assertEqual(self.window.preferences['theme'], 'dark')

    def test_close_apply_commits_before_closing(self):
        self.page.show()
        self.choose('theme', 'light')
        def apply(box):
            for button in box.buttons():
                if button.text() == 'Aplicar':
                    button.click()
        with patch.object(QMessageBox, 'exec', apply):
            self.page.reject()
        self.assertFalse(self.page.isVisible())
        self.assertEqual(self.window.ui_settings.load()['theme'], 'light')

    def test_system_theme_changes_reapply_only_when_selected(self):
        from clipx.ui.foundations.appearance import is_light
        from PyQt6.QtCore import Qt
        values = {**DEFAULT_UI, 'theme': 'system'}
        with patch.object(QApplication.styleHints(), 'colorScheme', return_value=Qt.ColorScheme.Light):
            self.window.apply_preferences(values)
            self.assertTrue(self.window.property('lightTheme'))
            self.assertTrue(is_light(values))
        with patch.object(QApplication.styleHints(), 'colorScheme', return_value=Qt.ColorScheme.Dark):
            self.window.system_theme_changed()
            self.assertFalse(self.window.property('lightTheme'))

    def test_opaque_material_removes_native_effects(self):
        self.window.show()
        with patch.object(self.platform.effects, 'remove') as remove, patch.object(self.platform.effects, 'apply') as apply:
            self.window.apply_preferences({**DEFAULT_UI, 'material': 'opaque'})
        remove.assert_called_once_with(self.window)
        apply.assert_not_called()
        self.assertFalse(self.window.surface.property('nativeGlass'))
        self.window.close()

    def test_large_scale_preferences_keep_actions_accessible_at_minimum(self):
        self.page.show()
        self.choose('scale', 150)
        self.page.apply_changes()
        self.page.resize(820, 580)
        self.app.processEvents()
        self.app.processEvents()
        self.assertEqual(self.page.width(), 820)
        self.assertEqual(self.page.height(), 580)
        for button in (self.page.footer.reset, self.page.buttons.cancel, self.page.apply_button):
            point = button.mapTo(self.page, button.rect().center())
            self.assertTrue(self.page.rect().contains(point))
        self.assertEqual(self.page.pages['appearance'].horizontalScrollBar().maximum(), 0)
