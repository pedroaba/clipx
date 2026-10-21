"""Dialog shell using the running platform's native window decorations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from clipx.ui.foundations.fonts import install_fonts
from clipx.platforms.window_chrome import NativeChromeFilter
from clipx.ui.foundations.branding import app_icon
from clipx.platforms.dock import sync_dialog_dock


class SystemDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        install_fonts()
        self.setWindowIcon(app_icon())
        self.setProperty('clipxSettingsDialog', True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self._chrome = NativeChromeFilter(self)
        self.installEventFilter(self._chrome)

    def showEvent(self, event):
        super().showEvent(event)
        sync_dialog_dock()

    def hideEvent(self, event):
        super().hideEvent(event)
        sync_dialog_dock()

    def mount_content(self, content, maximize=True):
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, maximize)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(content)


def customize_message_box(box):
    """Keep native dialog decorations and standard QMessageBox behavior."""
    install_fonts()
    box.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    box._chrome = NativeChromeFilter(box)
    box.installEventFilter(box._chrome)
    return box
