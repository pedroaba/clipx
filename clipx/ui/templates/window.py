"""Dialog shell using the running platform's native window decorations."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QVBoxLayout
from clipx.ui.foundations.fonts import install_fonts
from clipx.platforms.window_chrome import NativeChromeFilter
from clipx.ui.foundations.branding import app_icon
from clipx.platforms.dock import sync_dialog_dock


class SystemDialog(QDialog):
    """Dialog shell that keeps the running platform's native window chrome.

    The dialog installs application fonts, applies the ClipX icon and settings
    property, explicitly disables frameless and always-on-top flags, and
    installs a :class:`NativeChromeFilter` event filter for platform-specific
    decoration handling.
    """

    def __init__(self, parent=None):
        """Create the dialog shell and its native chrome filter.

        Args:
            parent (QWidget, optional): Parent widget that owns the dialog.
        """
        super().__init__(parent)
        install_fonts()
        self.setWindowIcon(app_icon())
        self.setProperty('clipxSettingsDialog', True)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self._chrome = NativeChromeFilter(self)
        self.installEventFilter(self._chrome)

    def showEvent(self, event):
        """Synchronize dock visibility when the dialog is shown.

        Args:
            event (QShowEvent): Show event forwarded to the base class.
        """
        super().showEvent(event)
        sync_dialog_dock()

    def hideEvent(self, event):
        """Synchronize dock visibility when the dialog is hidden.

        Args:
            event (QHideEvent): Hide event forwarded to the base class.
        """
        super().hideEvent(event)
        sync_dialog_dock()

    def mount_content(self, content, maximize=True):
        """Add the main content and enable the appropriate window buttons.

        Args:
            content (QWidget): Widget placed in the dialog's outer layout.
            maximize (bool, optional): Whether to show the maximize button.
                Defaults to True.
        """
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, maximize)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(content)


def customize_message_box(box):
    """Keep native dialog decorations and standard QMessageBox behavior.

    Args:
        box (QMessageBox): Message box to configure in place.

    Returns:
        QMessageBox: The same box, after installing fonts, clearing frameless
            and always-on-top flags, and attaching a native chrome filter.
    """
    install_fonts()
    box.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
    box._chrome = NativeChromeFilter(box)
    box.installEventFilter(box._chrome)
    return box
