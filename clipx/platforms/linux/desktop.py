"""Linux activation lifecycle and asynchronous automatic paste integration."""
import logging
import os
import shutil
import subprocess
import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QApplication
from clipx.platforms.base import Result, Status
from .processes import helper_environment

logger = logging.getLogger('clipx.desktop')
MANUAL_PASTE = 'Conteúdo copiado. Não foi possível colar automaticamente; use Ctrl+V.'


def is_gnome_wayland():
    """Detect the desktop session independently of an XWayland DISPLAY."""
    session = os.environ.get('XDG_SESSION_TYPE', '').lower()
    wayland = session == 'wayland' or (not session and bool(os.environ.get('WAYLAND_DISPLAY')))
    desktop = ':'.join(os.environ.get(key, '') for key in (
        'XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')).lower()
    return wayland and any(name in desktop for name in ('gnome', 'ubuntu'))


def _run_paste_tool(command, cancelled):
    """Run a helper for at most two seconds, terminating it when focus returns."""
    process = subprocess.Popen(command, env=helper_environment(),
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 2
    try:
        while True:
            if cancelled is not None and cancelled.is_set():
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command[0], 2)
            try:
                _, stderr = process.communicate(timeout=min(.05, remaining))
                return subprocess.CompletedProcess(command, process.returncode, stderr=stderr)
            except subprocess.TimeoutExpired:
                continue
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()


def paste_to_active_window(cancelled=None):
    """Try compatible input tools with bounded waits and failure fallback.

    GNOME/Wayland uses ydotool; other sessions try wtype then ydotool. No
    command inherits startup tokens, and diagnostics never contain clipboard
    contents. Cancellation is checked before each attempt.

    Args:
        cancelled (threading.Event | None): Set when search regains focus.

    Returns:
        bool: Whether a helper reported successful key injection.
    """
    commands = [('wtype', ['-M', 'ctrl', '-k', 'v', '-m', 'ctrl']),
                ('ydotool', ['key', '29:1', '47:1', '47:0', '29:0'])]
    if is_gnome_wayland():
        commands = commands[1:]
    for tool, args in commands:
        if cancelled is not None and cancelled.is_set():
            return False
        if not shutil.which(tool):
            logger.info('Automatic paste backend %s is not installed', tool)
            continue
        try:
            result = _run_paste_tool([tool, *args], cancelled)
            if result is None:
                return False
            if result.returncode == 0:
                return True
            logger.warning('Automatic paste backend %s exited with code %s: %s',
                           tool, result.returncode, (result.stderr or '').strip()[:300])
        except subprocess.TimeoutExpired:
            logger.warning('Automatic paste backend %s timed out', tool)
        except OSError as exc:
            logger.warning('Automatic paste backend %s could not start: %s', tool, exc)
    return False


class LinuxDesktopDriver(QObject):
    """Own activation announcements and deliver paste results on the Qt thread."""

    _paste_ready = pyqtSignal(object, object)

    def __init__(self):
        """Initialize one-shot activation state and a cancellable paste request."""
        super().__init__()
        self.startup_id = ''
        self._activation_token = ''
        self._pending_startups = set()
        self._finished_startups = set()
        self._paste_cancelled = threading.Event()
        self._paste_ready.connect(self._deliver_paste, Qt.ConnectionType.QueuedConnection)

    def remember_target(self):
        """Rely on GNOME restoring focus when the search overlay is hidden."""
        pass

    def activation_token(self):
        """Keep a startup ID separate from a native Wayland activation token."""
        from .activation import activation_token_for_launch
        inherited = os.environ.get('XDG_ACTIVATION_TOKEN') or os.environ.get('DESKTOP_STARTUP_ID')
        self._activation_token = activation_token_for_launch()
        self.startup_id = (os.environ.get('DESKTOP_STARTUP_ID', '') if inherited
                           else self._activation_token)
        return self._activation_token

    def finish_startup(self, startup_id):
        """Complete a known announcement once, including setup failure paths."""
        if not startup_id or startup_id in self._finished_startups:
            return
        from .activation import finish_startup
        finish_startup(startup_id)
        self._finished_startups.add(startup_id)
        self._pending_startups.discard(startup_id)
        if startup_id == self.startup_id:
            self.startup_id = ''
            self._activation_token = ''

    def open_search(self, window, activation_token='', startup_id=''):
        """Show search and end its startup sequence after Qt handles the show.

        Args:
            window (QWidget): Search or settings window to activate.
            activation_token (str): Native or XWayland token used for focus.
            startup_id (str): Explicit X11 announcement ID, possibly from IPC.
        """
        self.cancel_paste()
        if not activation_token and QApplication.platformName().startswith('wayland'):
            activation_token = self.activation_token()
        if not startup_id and activation_token == self._activation_token:
            startup_id = self.startup_id
        if startup_id:
            self._pending_startups.add(startup_id)
        was_visible = window.isVisible()
        if activation_token:
            os.environ['XDG_ACTIVATION_TOKEN'] = activation_token
        try:
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            window.showNormal()
            window.raise_()
            if was_visible or not (activation_token and QApplication.platformName().startswith('wayland')):
                window.activateWindow()
        except BaseException:
            self.finish_startup(startup_id)
            raise
        else:
            if startup_id:
                QTimer.singleShot(0, lambda: self._finish_pending(startup_id))
        finally:
            os.environ.pop('XDG_ACTIVATION_TOKEN', None)
            os.environ.pop('DESKTOP_STARTUP_ID', None)

    def _finish_pending(self, startup_id):
        """Avoid duplicate completions if shutdown preceded a queued show callback."""
        if startup_id in self._pending_startups:
            self.finish_startup(startup_id)

    def cancel_paste(self):
        """Cancel pending paste and stop a helper that is still running."""
        self._paste_cancelled.set()

    def paste_to_previous(self, callback=None):
        """Inject paste in a worker and deliver its outcome on the owning thread.

        Args:
            callback (callable | None): Receives the eventual Result on Qt's
                thread. Without a callback, run synchronously.

        Returns:
            Result: Immediate pending success, or the synchronous result.
        """
        self.cancel_paste()
        cancelled = self._paste_cancelled = threading.Event()

        def perform():
            """Map a bounded helper invocation to an operation result."""
            try:
                succeeded = paste_to_active_window(cancelled)
            except Exception:
                logger.exception('Automatic paste failed before completion')
                succeeded = False
            if succeeded and not cancelled.is_set():
                return Result()
            code = 'paste_cancelled' if cancelled.is_set() else 'paste_unavailable'
            return Result(Status.UNAVAILABLE, MANUAL_PASTE, code)

        if callback is None:
            return perform()

        def run():
            """Publish completion through a persistent QObject signal carrier."""
            self._paste_ready.emit(callback, perform())

        threading.Thread(target=run, daemon=True).start()
        return Result()

    def _deliver_paste(self, callback, result):
        """Invoke the consumer on the Qt thread even after the worker exits."""
        callback(result)

    def stop(self):
        """Cancel pending paste and finish any outstanding startup announcements."""
        self.cancel_paste()
        for startup_id in tuple(self._pending_startups):
            self.finish_startup(startup_id)
