"""Inline feedback occupies space only when a message is present."""
from PyQt6.QtWidgets import QLabel


class FeedbackLabel(QLabel):
    """Inline message label that occupies layout space only when it has text.

    The label uses the ``InlineFeedback`` object name for theming, enables word
    wrapping, and starts hidden so an empty message does not leave a gap.
    """

    def __init__(self, parent=None):
        """Create a hidden, word-wrapped inline feedback label.

        Args:
            parent (QWidget, optional): Parent widget that owns the label.
        """
        super().__init__(parent)
        self.setObjectName('InlineFeedback')
        self.setWordWrap(True)
        self.hide()

    def setText(self, text):
        """Set the message and show the label only when text is non-empty.

        Args:
            text (str): Message to display; an empty string hides the label.
        """
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self):
        """Remove the message, which also hides the label."""
        self.setText('')
