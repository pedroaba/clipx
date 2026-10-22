"""Linux focus and paste integration.

Activates the search window using XDG activation tokens and optionally injects
Ctrl+V into the previously active application through ``wtype`` or ``ydotool``.
"""
import os
import shutil
import subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from clipx.platforms.base import Result, Status

def paste_to_active_window():
    """Simulates Ctrl+V into the active application if tools are installed.

    Tries ``wtype`` first and falls back to ``ydotool`` when ``wtype`` is not
    installed. Both tools run with a two second timeout, and any exception is
    swallowed.

    Returns:
        bool: ``True`` if the tool exited successfully, otherwise ``False``.
    """
    if shutil.which("wtype"):
        try:
            result = subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"], timeout=2, check=False)
            return result.returncode == 0
        except Exception:
            pass
    elif shutil.which("ydotool"):
        try:
            result = subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"], timeout=2, check=False)
            return result.returncode == 0
        except Exception:
            pass
    return False



class LinuxDesktopDriver:
    """Window activation and automatic paste integration for Linux.

    Activation relies on XDG activation tokens, obtained either from the
    environment or announced through XWayland when needed.
    """
    def remember_target(self):
        """Do nothing, because the Linux backend does not track a target window."""
        pass

    def activation_token(self):
        """Return an activation token for opening a window.

        Returns:
            str: Token from :func:`activation_token_for_launch`, possibly empty.
        """
        from .activation import activation_token_for_launch
        return activation_token_for_launch()

    def open_search(self, window, activation_token=""):
        """Show and activate the search window.

        On Wayland without an explicit token, one is requested first. The token
        is exported as ``XDG_ACTIVATION_TOKEN`` while the window is shown and
        removed afterwards. With a token on Wayland, an already visible window
        is activated; a newly shown window relies on the token instead. The
        ``WA_ShowWithoutActivating`` attribute is cleared so the window may take
        focus.

        Args:
            window (QWidget): Window to show and raise.
            activation_token (str): Optional pre-obtained activation token.
        """
        if not activation_token and QApplication.platformName().startswith("wayland"):
            activation_token = self.activation_token()
        was_visible = window.isVisible()
        if activation_token:
            os.environ["XDG_ACTIVATION_TOKEN"] = activation_token
        try:
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            window.showNormal()
            window.raise_()
            if was_visible or not (activation_token and QApplication.platformName().startswith("wayland")):
                window.activateWindow()
        finally:
            if activation_token:
                os.environ.pop("XDG_ACTIVATION_TOKEN", None)

    def paste_to_previous(self, callback=None):
        """Copy the selected text into the previously active application.

        Args:
            callback (callable | None): Callback invoked on the GUI thread with
                the resulting :class:`Result`. When omitted, the paste is
                attempted synchronously and its result returned.

        Returns:
            Result: With a callback, an immediately returned success result that
                does not reflect the paste; without one, the actual paste
                result. A failed automatic paste yields an ``UNAVAILABLE``
                result telling the user to paste manually.
        """
        # Running subprocess tools off the GUI thread keeps search responsive.
        def perform():
            """Attempt the paste and map the outcome to a result.

            Returns:
                Result: Success, or an unavailable result when no tool worked.
            """
            if paste_to_active_window():
                return Result()
            return Result(Status.UNAVAILABLE, "Texto copiado. Cole no aplicativo de destino; colagem automática indisponível.")
        if callback is None:
            return perform()
        from PyQt6.QtCore import QObject, pyqtSignal, Qt
        import threading
        class Delivery(QObject):
            """Signal carrier that delivers a result back to the GUI thread.

            Attributes:
                finished (pyqtSignal): Emits the paste :class:`Result`.
            """
            finished = pyqtSignal(object)
        delivery = Delivery()
        delivery.finished.connect(callback, Qt.ConnectionType.QueuedConnection)
        def run():
            """Run the paste in the worker thread and emit its result."""
            delivery.finished.emit(perform())
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return Result()
