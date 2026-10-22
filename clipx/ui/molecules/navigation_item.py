"""Sidebar navigation item: icon, name, and an actual action count."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QLabel
from clipx.ui.foundations.icons import icon


class NavigationItem(QPushButton):
    """Checkable sidebar button with an icon, title, and shortcut counter.

    Child labels are transparent to mouse events so the button receives all
    clicks. The accessible name combines the visible title and count.
    """

    def __init__(self, label, glyph, count, parent=None):
        """Create a navigation item and render its initial state.

        Args:
            label (str): Visible title used in the accessible name.
            glyph (str): Icon identifier resolved by the foundations icon
                helper.
            count (int): Number of shortcuts shown in the counter.
            parent (QWidget, optional): Parent widget that owns the item.
        """
        super().__init__(parent)
        self.setObjectName('NavigationItem')
        self.setCheckable(True)
        self.setAutoDefault(False)
        self.setMinimumHeight(42)
        box = QHBoxLayout(self)
        box.setContentsMargins(12, 0, 12, 0)
        box.setSpacing(10)
        self.glyph = glyph
        self.image = QLabel()
        self.title = QLabel(label)
        self.title.setObjectName('NavigationTitle')
        self.counter = QLabel(str(count))
        self.counter.setObjectName('NavigationCount')
        for widget in (self.image, self.title, self.counter):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        box.addWidget(self.image)
        box.addWidget(self.title, 1)
        box.addWidget(self.counter)
        self.setAccessibleName(f'{label}, {count} atalhos')

        self.toggled.connect(self.refresh_state)
        self.refresh_state(False)

    def refresh_state(self, checked):
        """Apply the active property and icon color for the checked state.

        Args:
            checked (bool): Whether the navigation item is selected.
        """
        for widget in (self.title, self.counter):
            widget.setProperty('active', checked)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.image.setPixmap(icon(self.glyph, 18, '#F4F4F5' if checked else '#A1A1AA').pixmap(18, 18))
