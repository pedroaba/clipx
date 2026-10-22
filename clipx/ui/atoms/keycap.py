"""A single keyboard key, with text also exposed to accessibility APIs."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel


class Keycap(QLabel):
    """A single keyboard key rendered as a styled, non-interactive label.

    The key text is centered, given a minimum size, made transparent to mouse
    events, and exposed as the accessible name so assistive technologies read
    the key instead of only painting it.
    """

    def __init__(self, text, parent=None):
        """Create a keycap displaying ``text``.

        Args:
            text (str): Key label shown in the widget and accessible name.
            parent (QWidget, optional): Parent widget that owns the keycap.
        """
        super().__init__(text, parent)
        self.setObjectName('Keycap')
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(25, 27)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAccessibleName(text)
