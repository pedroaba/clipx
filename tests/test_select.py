"""Shared select behavior, preserving Qt data and keyboard interaction."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import unittest
from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStyle
from clipx.ui.molecules.select import Select


class SelectTests(unittest.TestCase):
    """Check popup selection keeps item data and emits the expected signals."""

    @classmethod
    def setUpClass(cls):
        """Create the shared offscreen QApplication."""
        cls.app = QApplication.instance() or QApplication([])

    def test_popup_keyboard_selection_preserves_values_and_signals(self):
        """Keyboard navigation selects the item data, emits once and Escape cancels."""
        select = Select(heading="Filtrar por tipo")
        try:
            select.addItem('Todos', 'all')
            select.addItem('Código', 'code')
            changed = []
            select.currentIndexChanged.connect(changed.append)
            select.show()
            select.showPopup()
            QTest.keyClick(select.view(), Qt.Key.Key_Down)
            QTest.keyClick(select.view(), Qt.Key.Key_Return)
            self.assertEqual(select.view().heading.text(), 'Filtrar por tipo')
            self.assertEqual(select.currentData(), 'code')
            self.assertEqual(changed, [1])
            self.assertFalse(select.view().isVisible())
            select.showPopup()
            QTest.keyClick(select.view(), Qt.Key.Key_Escape)
            self.assertEqual(select.currentData(), 'code')
            self.assertFalse(select.view().isVisible())
            self.assertEqual(select.style().styleHint(QStyle.StyleHint.SH_ComboBox_Popup), 0)
        finally:
            select.close()
            select.deleteLater()
