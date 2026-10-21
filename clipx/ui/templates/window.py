"""Dialog shell using the running platform's native window decorations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from clipx.ui.foundations.fonts import install_fonts
from clipx.platforms.window_chrome import NativeChromeFilter


class SystemDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        install_fonts()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self._chrome = NativeChromeFilter(self)
        self.installEventFilter(self._chrome)

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
