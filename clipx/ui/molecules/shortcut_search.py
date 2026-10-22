"""Search field for filtering shortcut preferences by name or combination."""
from PyQt6.QtCore import pyqtSignal, QEvent
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit
from clipx.ui.foundations.icons import label_icon
from clipx.ui.molecules.keycaps import ShortcutKeycaps


class ShortcutSearch(QFrame):
    """Themed shortcut search box with a search icon and keycap hint.

    Attributes:
        query_changed (pyqtSignal): Emitted whenever the input text changes.
    """

    query_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        """Create the input, its icon, and the Ctrl+F hint.

        Args:
            parent (QWidget, optional): Parent widget that owns the search box.
        """
        super().__init__(parent)
        self.setObjectName('ShortcutSearch')
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 0, 10, 0)
        box.setSpacing(10)
        image = QLabel()
        label_icon(image, 'search', 17)
        box.addWidget(image)
        self.input = QLineEdit()
        self.input.setObjectName('ShortcutSearchInput')
        self.input.setPlaceholderText('Buscar atalho…')
        self.input.setAccessibleName('Buscar atalhos por nome ou combinação de teclas')
        self.input.setClearButtonEnabled(True)
        self.input.installEventFilter(self)
        self.input.textChanged.connect(self.query_changed)
        box.addWidget(self.input, 1)
        box.addWidget(ShortcutKeycaps('Ctrl+F'))
        self.setMinimumHeight(42)

    def eventFilter(self, obj, event):
        """Toggle the ``focused`` style property as the input gains or loses focus.

        Args:
            obj (QObject): Object that emitted the event.
            event (QEvent): Event being filtered.

        Returns:
            bool: The base class result; focus events are not consumed.
        """
        if obj is self.input and event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            self.setProperty('focused', event.type() == QEvent.Type.FocusIn)
            self.style().unpolish(self)
            self.style().polish(self)
        return super().eventFilter(obj, event)
