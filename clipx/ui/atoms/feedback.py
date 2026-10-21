"""Inline feedback occupies space only when a message is present."""
from PyQt6.QtWidgets import QLabel


class FeedbackLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('InlineFeedback')
        self.setWordWrap(True)
        self.hide()

    def setText(self, text):
        super().setText(text)
        self.setVisible(bool(text))

    def clear(self):
        self.setText('')
