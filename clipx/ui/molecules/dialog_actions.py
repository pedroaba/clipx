"""Explicit secondary/primary actions, ordered like the preferences reference."""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QPushButton, QHBoxLayout


class DialogActions(QWidget):
    accepted = pyqtSignal()
    rejected = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        box = QHBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)
        self.cancel = QPushButton('Cancelar')
        self.cancel.setObjectName('CancelPreferences')
        self.cancel.setAutoDefault(False)
        self.cancel.clicked.connect(self.rejected)
        self.apply = QPushButton('Aplicar')
        self.apply.setObjectName('ApplyButton')
        self.apply.setAutoDefault(False)
        self.apply.clicked.connect(self.accepted)
        box.addWidget(self.cancel)
        box.addWidget(self.apply)
