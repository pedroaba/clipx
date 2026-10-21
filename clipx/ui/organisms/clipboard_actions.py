from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip
from PyQt6.QtGui import QKeySequence
from clipx.shortcuts import DEFAULT_SHORTCUTS


class ActionBarWidget(QFrame):
    primary_requested = pyqtSignal()
    actions_requested = pyqtSignal()

    def __init__(self, parent=None, shortcuts=None):
        super().__init__(parent)
        self.setObjectName('ActionBar')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 7, 12, 7)
        layout.setSpacing(8)
        brand = QLabel('ClipX')
        brand.setObjectName('Secondary')
        layout.addWidget(brand)
        layout.addStretch()
        self.primary = QPushButton('Copiar e colar')
        self.primary.clicked.connect(self.primary_requested)
        layout.addWidget(self.primary)
        self.key_labels = {}
        for name in DEFAULT_SHORTCUTS:
            label = QLabel(self)
            label.setProperty('class', 'KeyBadge')
            self.key_labels[name] = label
            if name == 'copy':
                layout.addWidget(label)
            else:
                label.hide()
        divider = QLabel('│')
        divider.setObjectName('Secondary')
        layout.addWidget(divider)
        self.actions = QPushButton('Ações')
        self.actions.setAccessibleName('Abrir ações do item selecionado')
        self.actions.clicked.connect(self.actions_requested)
        layout.addWidget(self.actions)
        keys = QLabel(QKeySequence('Ctrl+K').toString(QKeySequence.SequenceFormat.NativeText))
        keys.setProperty('class', 'KeyBadge')
        layout.addWidget(keys)
        grip = QSizeGrip(self)
        grip.setAccessibleName("Redimensionar janela")
        grip.setFixedSize(12, 12)
        layout.addWidget(grip)
        self.update_shortcuts(shortcuts or DEFAULT_SHORTCUTS)

    def update_shortcuts(self, values):
        for name, label in self.key_labels.items():
            value = values.get(name, '')
            label.setText(QKeySequence(value).toString(QKeySequence.SequenceFormat.NativeText) if value else '—')
        self.actions.setToolTip('Fixar: ' + self.key_labels['pin'].text() + ' · Excluir: ' + self.key_labels['delete'].text())
