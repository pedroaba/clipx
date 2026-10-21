"""Search and copy behavior with injected system drivers; no real clipboard access."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from clipx.platforms.base import Result, Status
from clipx.platforms.effects import OpaqueWindowEffects
from clipx.services import ClipboardService
from clipx.storage import Storage
from clipx.shortcuts import ShortcutSettings
from clipx.ui.pages.clipboard import ClipXMainWindow


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Storage(Path(self.temp.name) / 'history.db')
        self.platform = SimpleNamespace(name='test', clipboard=Mock(), desktop=Mock(), effects=OpaqueWindowEffects())
        self.platform.clipboard.write_text.return_value = Result()
        self.window = ClipXMainWindow(self.storage, ShortcutSettings(Path(self.temp.name) / 'settings.json'), self.platform)
        self.addCleanup(self.window.deleteLater)
        self.addCleanup(self.window.close)

    def test_copy_failure_keeps_window_and_does_not_update_recency(self):
        self.storage.add_clip('keep this')
        self.window.load_clips()
        self.window.show()
        old = self.storage.get_clips()[0].updated_at
        self.platform.clipboard.write_text.return_value = Result(Status.ERROR, 'Cópia falhou')
        self.window._action_select_and_copy()
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.storage.get_clips()[0].updated_at, old)
        self.assertEqual(self.window.status_label.text(), 'Cópia falhou')
        self.platform.desktop.paste_to_previous.assert_not_called()

    def test_copy_only_writes_full_text_and_never_pastes(self):
        self.storage.add_clip('Olá\n世界\n')
        self.window.load_clips()
        self.window.show()
        self.window._copy_selected(paste=False)
        self.platform.clipboard.write_text.assert_called_once_with('Olá\n世界\n')
        self.platform.desktop.paste_to_previous.assert_not_called()
        self.assertFalse(self.window.isVisible())

    def test_refresh_preserves_selection_query_and_scroll(self):
        for n in range(30):
            self.storage.add_clip(f'text {n}')
        self.window._on_search_query_changed('text')
        self.window.show()
        self.app.processEvents()
        self.window.clip_list.setCurrentRow(12)
        clip = self.window.clip_list.get_selected_clip()
        self.window.clip_list.verticalScrollBar().setValue(120)
        scroll = self.window.clip_list.verticalScrollBar().value()
        self.storage.add_clip('text new')
        self.window.load_clips()
        self.assertEqual(self.window.current_query, 'text')
        self.assertEqual(self.window.clip_list.get_selected_clip().id, clip.id)
        self.assertEqual(self.window.clip_list.verticalScrollBar().value(), scroll)

    def test_empty_and_no_results_and_capture_status_are_distinct(self):
        self.assertIn('histórico está vazio', self.window.clip_list.empty_label.text())
        self.window._on_search_query_changed('absent')
        self.assertIn('Nenhum resultado', self.window.clip_list.empty_label.text())
        self.window.set_capture_status(Result(Status.UNAVAILABLE, 'Captura pausada'))
        self.assertEqual(self.window.status_label.text(), 'Captura pausada')
        self.window.show_result(Result(Status.ERROR, 'Falha de cópia'))
        self.window.clear_feedback()
        self.assertEqual(self.window.status_label.text(), 'Captura pausada')

    def test_actions_are_available_and_disabled_without_selection(self):
        self.window.open_actions()
        self.assertTrue(all(not a.isEnabled() for a in self.window.actions_menu.actions() if not a.isSeparator()))
        self.window.actions_menu.close()
        self.storage.add_clip('action target')
        self.window.load_clips()
        self.window.open_actions()
        self.assertTrue(all(a.isEnabled() for a in self.window.actions_menu.actions() if not a.isSeparator()))
        self.window.actions_menu.close()

    def test_html_in_text_is_displayed_literally(self):
        self.storage.add_clip('<b>literal</b>\n  preserve spaces', clip_type='text')
        self.window.load_clips()
        self.assertEqual(self.window.preview_pane.text_browser.toPlainText(), '<b>literal</b>\n  preserve spaces')

    def test_deactivation_closes_search_without_quitting_application(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtTest import QTest
        self.window.show()
        with patch.object(self.window, 'isActiveWindow', return_value=False), \
             patch.object(QApplication, 'activePopupWidget', return_value=None), \
             patch.object(QApplication, 'activeModalWidget', return_value=None):
            self.app.sendEvent(self.window, QEvent(QEvent.Type.WindowDeactivate))
            QTest.qWait(130)
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.app.quitOnLastWindowClosed())

    def test_owned_actions_popup_does_not_dismiss_search(self):
        self.window.show()
        with patch.object(self.window, 'isActiveWindow', return_value=False), \
             patch.object(QApplication, 'activePopupWidget', return_value=self.window.actions_menu):
            self.window.dismiss_if_inactive()
        self.assertTrue(self.window.isVisible())

    def test_geist_is_loaded_locally_and_window_stays_opaque(self):
        from PyQt6.QtGui import QFontInfo
        self.window.show()
        self.assertEqual(self.window.windowOpacity(), 1.0)
        self.assertTrue(self.window.surface.testAttribute(Qt.WidgetAttribute.WA_StyledBackground))
        self.app.processEvents()
        background = self.window.surface.grab().toImage().pixelColor(5, 100)
        self.assertGreaterEqual(background.alpha(), 238)
        self.assertLess(background.red(), 40)
        self.assertEqual(QFontInfo(self.window.search_bar.input_field.font()).family(), 'Geist')
        self.storage.add_clip('print("Geist Mono")', clip_type='code', language='python')
        self.window.load_clips()
        self.assertEqual(QFontInfo(self.window.preview_pane.text_browser.font()).family(), 'Geist Mono')

    def test_search_has_no_titlebar_and_close_keeps_application_running(self):
        self.window.show()
        self.assertFalse(hasattr(self.window.surface, 'title_bar'))
        self.assertTrue(self.window.windowFlags() & Qt.WindowType.FramelessWindowHint)
        self.window.close()
        self.assertFalse(self.window.isVisible())
        self.assertFalse(self.app.quitOnLastWindowClosed())

    def test_typing_survives_repeated_activation_and_result_refresh(self):
        from PyQt6.QtCore import QEvent
        from PyQt6.QtTest import QTest
        self.storage.add_clip('pesquisa de exemplo')
        self.window.show()
        field = self.window.search_bar.input_field
        with patch.object(self.window, 'isActiveWindow', return_value=True):
            for letter in 'pesquisa':
                QTest.keyClicks(field, letter)
                self.window.changeEvent(QEvent(QEvent.Type.ActivationChange))
                self.window.load_clips()
        self.assertEqual(field.text(), 'pesquisa')
        self.assertEqual(self.window.current_query, 'pesquisa')
        self.assertEqual(field.selectedText(), '')
        self.assertEqual(field.cursorPosition(), len('pesquisa'))

    def test_refocusing_search_preserves_cursor_and_selected_range(self):
        from PyQt6.QtTest import QTest
        self.window.show()
        field = self.window.search_bar.input_field
        field.setText('pesquisa')
        field.setCursorPosition(3)
        self.window.search_bar.focus_input()
        self.assertEqual(field.cursorPosition(), 3)
        self.assertEqual(field.selectedText(), '')
        QTest.keyClicks(field, 'X')
        self.assertEqual(field.text(), 'pesXquisa')
        field.setSelection(1, 3)
        self.window.search_bar.focus_input()
        self.assertEqual(field.selectedText(), 'esX')

    def test_typing_reuses_rows_and_preview_for_unchanged_results(self):
        for number in range(120):
            self.storage.add_clip(f'pesquisa exemplo {number}')
        self.window.load_clips()
        selected = self.window.clip_list.currentItem()
        widget = self.window.clip_list.itemWidget(selected)
        with patch.object(self.window.clip_list, '_insert_clip', wraps=self.window.clip_list._insert_clip) as insert, \
             patch.object(self.window.preview_pane, 'display_item', wraps=self.window.preview_pane.display_item) as preview:
            for query in ('p', 'pe', 'pes', 'pesq', 'pesquisa'):
                self.window.search_bar.input_field.setText(query)
            insert.assert_not_called()
            preview.assert_not_called()
        self.assertIs(self.window.clip_list.currentItem(), selected)
        self.assertIs(self.window.clip_list.itemWidget(selected), widget)

    def test_narrowing_and_expanding_only_constructs_new_results(self):
        for number in range(20):
            self.storage.add_clip(f'grupo {"A" if number % 2 else "B"} item {number}')
        self.window.load_clips()
        self.window.clip_list.setCurrentRow(0)
        selected = self.window.clip_list.currentItem()
        widget = self.window.clip_list.itemWidget(selected)
        with patch.object(self.window.clip_list, '_insert_clip', wraps=self.window.clip_list._insert_clip) as insert:
            self.window.search_bar.input_field.setText('grupo A')
            self.assertEqual(self.window.clip_list.count(), 10)
            insert.assert_not_called()
            self.assertIs(self.window.clip_list.currentItem(), selected)
            self.assertIs(self.window.clip_list.itemWidget(selected), widget)
            self.window.search_bar.input_field.clear()
            self.assertEqual(self.window.clip_list.count(), 20)
            self.assertEqual(insert.call_count, 10)
            self.assertIs(self.window.clip_list.currentItem(), selected)
        self.assertEqual([self.window.clip_list.item(i).data(Qt.ItemDataRole.UserRole).id
                          for i in range(self.window.clip_list.count())],
                         [item.id for item in self.storage.get_clips()])

    def test_incremental_refresh_handles_pin_reorder_deletion_and_empty_results(self):
        for number in range(5):
            self.storage.add_clip(f'item {number}')
        self.window.load_clips()
        self.window.clip_list.setCurrentRow(3)
        clip = self.window.clip_list.get_selected_clip()
        self.window._action_toggle_pin()
        self.assertEqual(self.window.clip_list.currentRow(), 0)
        self.assertEqual(self.window.clip_list.get_selected_clip().id, clip.id)
        self.assertTrue(self.window.clip_list.get_selected_clip().is_pinned)
        self.assertEqual(self.window.preview_pane.current_item.id, clip.id)
        self.window._action_delete()
        self.assertNotEqual(self.window.clip_list.get_selected_clip().id, clip.id)
        self.window.search_bar.input_field.setText('no matches')
        self.assertEqual(self.window.clip_list.count(), 0)
        self.assertIsNone(self.window.preview_pane.current_item)
        self.window.search_bar.input_field.clear()
        self.assertEqual(self.window.clip_list.count(), 4)
        self.assertIsNotNone(self.window.preview_pane.current_item)

    def test_same_code_preview_is_not_highlighted_again(self):
        self.storage.add_clip('def example():\n    return 1', 'code', 'python')
        self.window.load_clips()
        item = self.window.clip_list.get_selected_clip()
        with patch('clipx.ui.organisms.clipboard_preview.highlight') as highlight:
            self.window.preview_pane.display_item(item)
            self.window.search_bar.input_field.setText('def')
            self.window.search_bar.input_field.setText('example')
            highlight.assert_not_called()
        self.assertIn('return 1', self.window.preview_pane.text_browser.toPlainText())
