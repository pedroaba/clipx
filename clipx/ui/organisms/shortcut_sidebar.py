from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QButtonGroup
from clipx.ui.models.shortcut_catalog import CATEGORIES
from clipx.ui.molecules.navigation_item import NavigationItem


class ShortcutSidebar(QFrame):
    category_changed = pyqtSignal(str)

    def __init__(self, specs, parent=None):
        super().__init__(parent)
        self.setObjectName('PreferencesSidebar')
        self.setFixedWidth(190)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.buttons = {}
        self.counts = {'all': len(specs)}
        self.counts.update({name: sum(spec.category == name for spec in specs)
                           for name, _, _ in CATEGORIES if name != 'all'})
        for name, label, glyph in CATEGORIES:
            button = NavigationItem(label, glyph, self.counts[name])
            self.buttons[name] = button
            self.group.addButton(button)
            button.clicked.connect(lambda checked=False, category=name: self.category_changed.emit(category))
            layout.addWidget(button)
        self.buttons['all'].setChecked(True)
        layout.addStretch()
