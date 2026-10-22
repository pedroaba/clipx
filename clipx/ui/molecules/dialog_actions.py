"""Explicit secondary/primary actions, ordered like the preferences reference."""
from PyQt6.QtCore import QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon
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
        self.loading = False
        self._apply_enabled = True
        self._angle = 0
        self._spinner = QTimer(self)
        self._spinner.setInterval(40)
        self._spinner.timeout.connect(self._animate)

    def set_apply_enabled(self, enabled):
        self._apply_enabled = enabled
        self.apply.setEnabled(enabled and not self.loading)

    def _animate(self):
        from clipx.ui.foundations.icons import loading_icon
        from clipx.ui.foundations.appearance import palette_for
        values = self.window().window.preferences
        size = round(16 * values['scale'] / 100)
        self._angle = (self._angle + 18) % 360
        self.apply.setIcon(loading_icon(size, palette_for(values)['text'], self._angle))
        self.apply.setIconSize(QSize(size, size))

    def run_loading(self, action):
        # Preferences delegates shortcut persistence to the same action group.
        if self.loading:
            return action()
        self.loading = True
        cancel_enabled = self.cancel.isEnabled()
        self.cancel.setEnabled(False)
        self.apply.setEnabled(False)
        self.apply.setText('Aplicando…')
        self._angle = 0
        self._animate()
        window = self.window().window
        if window.preferences['motion'] != 'reduce' and not window.platform.effects.reduce_motion():
            self._spinner.start()
        self.apply.repaint()
        try:
            return action()
        finally:
            self._spinner.stop()
            self.loading = False
            self.apply.setIcon(QIcon())
            self.apply.setText('Aplicar')
            self.cancel.setEnabled(cancel_enabled)
            self.apply.setEnabled(self._apply_enabled)
