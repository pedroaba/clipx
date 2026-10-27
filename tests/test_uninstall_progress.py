"""Independent uninstall UI with fake actions; never accesses the clipboard."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import tempfile
import threading
import unittest

from PyQt6.QtTest import QTest, QSignalSpy
from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QApplication
from clipx.maintenance import MaintenanceResult
from clipx.ui.organisms.uninstall_progress import UninstallProgressDialog


class UninstallProgressTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name).resolve()

    def wait_for(self, condition):
        for _ in range(500):
            if condition():
                return
            QTest.qWait(10)
        self.fail('Independent uninstall UI did not finish')

    def test_ready_handshake_and_loading_survive_until_action_completes(self):
        gate = threading.Event()
        observed = []
        def action(progress):
            observed.append((self.folder / 'helper-ready').exists())
            progress('Removendo imagens de exemplo…')
            gate.wait(5)
            return MaintenanceResult(files=3, bytes=100)
        dialog = UninstallProgressDialog(self.folder, action, {'theme': 'dark', 'scale': 100}, success_delay_ms=None)
        completed = QSignalSpy(dialog.completed)
        try:
            dialog.show()
            self.wait_for(lambda: bool(observed))
            self.assertTrue(observed[0])
            self.assertEqual(dialog.progress.maximum(), 0)
            self.assertFalse(dialog.close_button.isEnabled())
            self.assertTrue(dialog.eventFilter(self.app, QEvent(QEvent.Type.Quit)))
            dialog.reject()
            self.assertTrue(dialog.isVisible())
            gate.set()
            self.wait_for(lambda: dialog.outcome is not None)
            self.assertEqual(dialog.outcome, 0)
            self.assertFalse(dialog.eventFilter(self.app, QEvent(QEvent.Type.Quit)))
            self.assertTrue(dialog.close_button.isEnabled())
            self.assertEqual((self.folder / 'ui-result-shown').read_text(), '0')
            dialog.close_button.click()
            self.assertEqual(list(completed[0]), [0])
            self.assertFalse(dialog.isVisible())
        finally:
            gate.set()
            dialog.worker.wait()
            dialog.reject()
            dialog.deleteLater()

    def test_success_closes_the_independent_window_automatically(self):
        dialog = UninstallProgressDialog(self.folder, lambda progress: MaintenanceResult(),
                                          {'theme': 'light', 'scale': 100}, success_delay_ms=1)
        completed = QSignalSpy(dialog.completed)
        dialog.show()
        self.wait_for(lambda: len(completed) == 1)
        self.assertEqual(list(completed[0]), [0])
        self.assertFalse(dialog.isVisible())
        dialog.worker.wait()
        dialog.deleteLater()

    def test_failure_remains_visible_without_a_success_message(self):
        def action(progress):
            raise OSError('Falha simulada antes da exclusão')
        dialog = UninstallProgressDialog(self.folder, action, {'theme': 'dark', 'scale': 100}, success_delay_ms=1)
        dialog.show()
        self.wait_for(lambda: dialog.outcome is not None)
        self.assertEqual(dialog.outcome, 1)
        self.assertEqual(dialog.heading.text(), 'Não foi possível concluir')
        self.assertIn('Falha simulada', dialog.status.text())
        QTest.qWait(50)
        self.assertTrue(dialog.isVisible())
        dialog.worker.wait()
        dialog.reject()
        dialog.deleteLater()


if __name__ == '__main__':
    unittest.main()
