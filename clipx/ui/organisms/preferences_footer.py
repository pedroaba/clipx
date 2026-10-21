from PyQt6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton


from clipx.ui.molecules.dialog_actions import DialogActions
from PyQt6.QtCore import Qt


class PreferencesFooter(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('PreferencesFooter')
        layout = QGridLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(12)
        self.reset = QPushButton('Restaurar padrões')
        self.reset.setObjectName('ResetPreferences')
        self.reset.setAutoDefault(False)
        layout.addWidget(self.reset, 0, 0)
        self.change_label = QLabel('Nenhuma alteração')
        self.change_label.setObjectName('PendingChanges')
        layout.addWidget(self.change_label, 0, 1)
        layout.setColumnStretch(1, 1)
        self.buttons = DialogActions()
        self.apply = self.buttons.apply
        layout.addWidget(self.buttons, 0, 2)
        self.set_pending(0)

    def set_pending(self, count, recording=False):
        self.change_label.setText('Nenhuma alteração' if not count else
            '1 alteração não salva' if count == 1 else f'{count} alterações não salvas')
        self.apply.setEnabled(count > 0 and not recording)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        scale = getattr(self.window(), 'window', None)
        scale = scale.preferences['scale'] / 100 if scale is not None else 1
        narrow = self.width() < 650 * scale
        self.layout().removeWidget(self.buttons)
        self.layout().addWidget(self.buttons, 1 if narrow else 0, 0 if narrow else 2,
                                1, 3 if narrow else 1, Qt.AlignmentFlag.AlignRight)
