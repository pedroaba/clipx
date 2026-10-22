"""Bottom action bar of the search window.

The bar exposes the primary copy action, the secondary actions menu and the
shortcut badges that mirror the currently configured key bindings.
"""
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizeGrip
from PyQt6.QtGui import QKeySequence
from clipx.shortcuts import DEFAULT_SHORTCUTS


class ActionBarWidget(QFrame):
    """Action bar with a primary copy button, a menu button and key badges.

    The widget only emits intent; the owning window decides what copying or
    opening the actions menu means. Only the copy badge is laid out inline,
    while the remaining badges are hidden and used as tooltip sources.

    Attributes:
        primary_requested (pyqtSignal): Emitted when the copy-and-paste button
            is clicked.
        actions_requested (pyqtSignal): Emitted when the actions button is
            clicked.
        primary (QPushButton): Button that triggers ``primary_requested``.
        key_labels (dict[str, QLabel]): Shortcut badges indexed by action name.
        actions (QPushButton): Button that triggers ``actions_requested``.
    """

    primary_requested = pyqtSignal()
    actions_requested = pyqtSignal()

    def __init__(self, parent=None, shortcuts=None):
        """Build the action bar and populate its shortcut badges.

        Args:
            parent (QWidget | None): Optional parent widget.
            shortcuts (dict[str, str] | None): Initial shortcut bindings; falls
                back to ``DEFAULT_SHORTCUTS`` when omitted.
        """
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
        """Refresh the badge texts and the actions tooltip from new bindings.

        Bindings are rendered in the platform's native key text; an empty
        binding is shown as an em dash.

        Args:
            values (dict[str, str]): Shortcut bindings indexed by action name.
        """
        for name, label in self.key_labels.items():
            value = values.get(name, '')
            label.setText(QKeySequence(value).toString(QKeySequence.SequenceFormat.NativeText) if value else '—')
        self.actions.setToolTip('Fixar: ' + self.key_labels['pin'].text() + ' · Excluir: ' + self.key_labels['delete'].text())
