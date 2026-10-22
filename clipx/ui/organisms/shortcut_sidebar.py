"""Category navigation for the shortcut dialog.

The sidebar only emits the selected category name; the controller decides how
rows are filtered.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QButtonGroup
from clipx.ui.models.shortcut_catalog import CATEGORIES
from clipx.ui.molecules.navigation_item import NavigationItem


class ShortcutSidebar(QFrame):
    """Fixed-width sidebar with one checkable navigation item per category.

    Attributes:
        category_changed (pyqtSignal): Emitted with the category key when a
            navigation item is clicked.
        group (QButtonGroup): Exclusive group holding every navigation item.
        buttons (dict[str, NavigationItem]): Items indexed by category key.
        counts (dict[str, int]): Number of shortcuts per category, plus ``all``.
    """

    category_changed = pyqtSignal(str)

    def __init__(self, specs, parent=None):
        """Create the navigation items and select the ``all`` category.

        Args:
            specs (list): Shortcut specifications used to compute the counts.
            parent (QWidget | None): Optional parent widget.
        """
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
