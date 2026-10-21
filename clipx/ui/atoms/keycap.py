"""A single keyboard key, with text also exposed to accessibility APIs."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel


class Keycap(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setObjectName('Keycap')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(25, 27)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName(text)
