"""Exclusive segmented choices with native button accessibility and keyboard focus."""
from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtWidgets import QBoxLayout, QButtonGroup, QFrame, QHBoxLayout, QSizePolicy, QToolButton


class SegmentedSelect(QFrame):
    currentIndexChanged = pyqtSignal(int)

    def __init__(self, choices, vertical_icons=False, parent=None):
        super().__init__(parent)
        self.setObjectName('SegmentedSelect')
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.choices = choices
        self.vertical_icons = vertical_icons
        self.buttons = []
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        for index, (label, value, glyph) in enumerate(choices):
            button = QToolButton()
            button.setObjectName('SegmentButton')
            button.setText(label)
            button.setAccessibleName(label)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding if vertical_icons else QSizePolicy.Policy.Ignored,
                                 QSizePolicy.Policy.Fixed)
            button.setMinimumHeight(64 if vertical_icons else 34)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if vertical_icons else Qt.ToolButtonStyle.ToolButtonTextOnly)
            if glyph:
                button.setProperty('glyphName', glyph)
            button.installEventFilter(self)
            self.group.addButton(button, index)
            self.buttons.append(button)
            layout.addWidget(button, 1)
        self.group.idToggled.connect(self._toggled)
        self.setCurrentIndex(0)

    def currentIndex(self):
        return self.group.checkedId()

    def currentData(self):
        return self.choices[self.currentIndex()][1]

    def findData(self, value):
        return next((index for index, choice in enumerate(self.choices) if choice[1] == value), -1)

    def setCurrentIndex(self, index):
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def _toggled(self, index, checked):
        if checked:
            for button in self.buttons:
                button.setFocusPolicy(Qt.FocusPolicy.StrongFocus if button.isChecked() else Qt.FocusPolicy.ClickFocus)
            self.currentIndexChanged.emit(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not self.vertical_icons:
            layout = self.layout()
            margins = layout.contentsMargins()
            required = sum(button.sizeHint().width() for button in self.buttons)
            required += margins.left() + margins.right() + layout.spacing() * (len(self.buttons) - 1)
            direction = QBoxLayout.Direction.TopToBottom if self.width() < required else QBoxLayout.Direction.LeftToRight
            if layout.direction() != direction:
                layout.setDirection(direction)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.KeyPress and watched in self.buttons:
            key = event.key()
            if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                       Qt.Key.Key_Home, Qt.Key.Key_End):
                index = self.currentIndex()
                if key == Qt.Key.Key_Home:
                    index = 0
                elif key == Qt.Key.Key_End:
                    index = len(self.buttons) - 1
                else:
                    direction = 1 if key in (Qt.Key.Key_Right, Qt.Key.Key_Down) else -1
                    if key in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.layoutDirection() == Qt.LayoutDirection.RightToLeft:
                        direction *= -1
                    index = (index + direction) % len(self.buttons)
                self.setCurrentIndex(index)
                self.buttons[index].setFocus()
                return True
        return super().eventFilter(watched, event)
