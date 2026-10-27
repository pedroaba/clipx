"""Confirmation semantics and explicit acceptance, using no real user data."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtTest import QTest, QSignalSpy
from PyQt6.QtWidgets import QApplication, QDialog, QWidget

from clipx.maintenance import MaintenanceResult, PruneOptions
from clipx.ui.organisms.maintenance_confirmation import (
    MaintenanceConfirmation, prune_confirmation, uninstall_confirmation)


class ConfirmationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.parent = QWidget()
        self.parent.resize(900, 700)
        self.parent.show()
        self.addCleanup(self.parent.deleteLater)
        self.addCleanup(self.parent.close)
        self.estimate = MaintenanceResult(items=20, files=1, bytes=220243)

    def make_dialog(self, spec=None, theme='dark', scale=100):
        spec = spec or prune_confirmation(PruneOptions('all', 'content'), self.estimate)
        dialog = MaintenanceConfirmation(spec, {'theme': theme, 'scale': scale}, self.parent)
        self.addCleanup(dialog.deleteLater)
        self.addCleanup(dialog.reject)
        return dialog

    def test_prune_summary_tracks_category_mode_and_pinned_scope(self):
        for target in ('all', 'data', 'images'):
            for mode in ('content', 'orphans'):
                for pinned in ((False, True) if mode == 'content' else (False,)):
                    with self.subTest(target=target, mode=mode, pinned=pinned):
                        spec = prune_confirmation(PruneOptions(target, mode, pinned), self.estimate)
                        self.assertIn('Os alvos serão recalculados', spec.details)
                        self.assertIn('clipboard serão mantidos', ' '.join(spec.preserved))
                        self.assertIn('originais externas serão preservadas', ' '.join(spec.preserved))
                        if mode == 'orphans':
                            self.assertIn('histórico válido', ' '.join(spec.preserved))
                            self.assertEqual(spec.effect_glyph, 'eraser')
                        elif pinned:
                            self.assertIn('Incluir os fixados', ' '.join(spec.effects))
                            self.assertNotIn('Fixados e suas imagens serão preservados.', spec.preserved)
                        else:
                            self.assertIn('Fixados e suas imagens serão preservados.', spec.preserved)

    def test_uninstall_summary_shows_real_paths_and_abbreviates_only_current_home(self):
        estimate = MaintenanceResult(paths=['/example/home/Library/Preferences/ClipX', '/example/home-other/clipx'])
        with patch('pathlib.Path.home', return_value=Path('/example/home')):
            spec = uninstall_confirmation(estimate)
        self.assertIn('~/Library/Preferences/ClipX', spec.details)
        self.assertIn('/example/home-other/clipx', spec.details)
        self.assertIn('incluindo fixados', ' '.join(spec.effects))
        self.assertIn('alterações pendentes', ' '.join(spec.effects))
        self.assertIn('clipboard', ' '.join(spec.effects))
        self.assertEqual(len(spec.preserved), 1)

    def test_escape_close_cancel_and_default_enter_reject_and_remove_dimming(self):
        for action in ('escape', 'close', 'cancel', 'enter'):
            with self.subTest(action=action):
                dialog = self.make_dialog()
                accepted = QSignalSpy(dialog.accepted)
                observed = {}
                def dismiss():
                    observed['focus'] = dialog.focusWidget() is dialog.cancel
                    observed['shade'] = dialog.shade is not None
                    if action == 'escape':
                        QTest.keyClick(dialog, Qt.Key.Key_Escape)
                    elif action == 'enter':
                        QTest.keyClick(dialog, Qt.Key.Key_Return)
                    elif action == 'close':
                        dialog.close_button.click()
                    else:
                        dialog.cancel.click()
                QTimer.singleShot(20, dismiss)
                self.assertEqual(dialog.exec(), QDialog.DialogCode.Rejected)
                self.assertTrue(observed['focus'])
                self.assertTrue(observed['shade'])
                self.assertEqual(len(accepted), 0)
                self.assertIsNone(dialog.shade)

    def test_explicit_destructive_button_accepts(self):
        for action in ('click', 'space', 'enter'):
            with self.subTest(action=action):
                dialog = self.make_dialog()
                def confirm():
                    if action == 'click':
                        dialog.confirm.click()
                    else:
                        dialog.confirm.setFocus()
                        QTest.keyClick(dialog.confirm, Qt.Key.Key_Space if action == 'space' else Qt.Key.Key_Return)
                QTimer.singleShot(20, confirm)
                self.assertEqual(dialog.exec(), QDialog.DialogCode.Accepted)
                self.assertIsNone(dialog.shade)

    def test_long_details_are_readonly_wrapped_and_actions_remain_visible_at_scale(self):
        estimate = MaintenanceResult(paths=['/very/long/' + 'directory-name/' * 40] * 10)
        for theme in ('dark', 'light'):
            with self.subTest(theme=theme):
                dialog = self.make_dialog(uninstall_confirmation(estimate), theme, 150)
                dialog.show()
                QTest.qWait(30)
                self.assertTrue(dialog.details.isReadOnly())
                self.assertIn(estimate.paths[0], dialog.details.toPlainText())
                self.assertEqual(dialog.details.horizontalScrollBar().maximum(), 0)
                self.assertTrue(dialog.confirm.isVisibleTo(dialog))
                self.assertLessEqual(dialog.height(), dialog.screen().availableGeometry().height())
                self.assertLessEqual(dialog.width(), dialog.screen().availableGeometry().width())
                self.assertGreater(dialog.confirm.width(), 100)
                dialog.reject()


if __name__ == '__main__':
    unittest.main()
