"""Linux focus and paste integration."""
import os
import shutil
import subprocess
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from clipx.platforms.base import Result, Status

def paste_to_active_window():
    """Simulates Ctrl+V into the active application if tools are installed."""
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
    def remember_target(self):
        pass

    def activation_token(self):
        from .activation import activation_token_for_launch
        return activation_token_for_launch()

    def open_search(self, window, activation_token=""):
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
        # Running subprocess tools off the GUI thread keeps search responsive.
        def perform():
            if paste_to_active_window():
                return Result()
            return Result(Status.UNAVAILABLE, "Texto copiado. Cole no aplicativo de destino; colagem automática indisponível.")
        if callback is None:
            return perform()
        from PyQt6.QtCore import QObject, pyqtSignal, Qt
        import threading
        class Delivery(QObject):
            finished = pyqtSignal(object)
        delivery = Delivery()
        delivery.finished.connect(callback, Qt.ConnectionType.QueuedConnection)
        def run():
            delivery.finished.emit(perform())
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return Result()
