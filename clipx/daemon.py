"""Background supervisor for the platform clipboard listener.

The daemon launches the platform-specific listener as a subprocess and forwards
its JSON status lines to Qt observers. It deliberately relies on event-based
listeners instead of polling, which would require disruptive popup windows on
Wayland.
"""

import json
import logging
import os
import signal
import subprocess
import sys
import threading
from typing import Optional

from clipx.storage import Storage
from clipx.maintenance_lock import registered_process
from clipx.platforms import get_platform
from clipx.platforms.base import Result, Status
from PyQt6.QtCore import QObject, pyqtSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clipx.daemon")


class ClipboardDaemon(QObject):
    """Supervise one event listener; never poll with Wayland popup windows.

    The daemon owns a listener subprocess, tracks capture status, and emits
    ``status_changed`` with the latest ``Result`` whenever that status changes.
    It starts, supervises, and stops a single background thread that reads the
    listener's output.

    Attributes:
        status_changed (pyqtSignal): Qt signal carrying the latest ``Result``.
        driver: Platform clipboard driver used to build the listener command.
        status (Result): Most recently reported capture status.
        storage (Storage): Storage used to locate the database passed to the
            listener and to persist captured clips.
        running (bool): True while the listener subprocess is active.
    """

    status_changed = pyqtSignal(object)

    def __init__(self, storage: Optional[Storage] = None, driver=None):
        """Initialize the daemon and its synchronization primitives.

        Args:
            storage (Optional[Storage]): Storage to use; a default ``Storage``
                is created when omitted.
            driver: Clipboard driver to use; the platform clipboard driver is
                resolved when omitted.
        """
        super().__init__()
        self.driver = driver or get_platform().clipboard
        self.status = Result(Status.UNAVAILABLE, "Iniciando captura…")
        self.storage = storage or Storage()
        self.running = False
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._process_lock = threading.Lock()

    def listener_command(self):
        """Build the subprocess command for the platform clipboard listener.

        Returns:
            The argument list produced by the driver for the current database
            path.
        """
        return self.driver.listener_command(self.storage.db_path)

    def report(self, result):
        """Store a capture status and notify listeners.

        Args:
            result (Result): Status object to record and emit.
        """
        self.status = result
        self.status_changed.emit(result)

    def run_loop(self):
        """Run the listener subprocess and forward its JSON status lines.

        The method blocks until the listener exits or fails to start. Malformed
        output lines are logged at debug level. When the listener stops without
        a stop request, the daemon reports that capture is paused. This method
        is intended to run on the daemon thread created by
        :meth:`start_background`.
        """
        try:
            with self._process_lock:
                if self._stop_event.is_set():
                    return
                self._process = subprocess.Popen(self.listener_command(), stdout=subprocess.PIPE, text=True, bufsize=1)
                self.running = True
            logger.info("ClipX event-based clipboard listener started.")
            self.report(Result())
            for line in self._process.stdout:
                try:
                    event = json.loads(line)
                    self.report(Result(Status(event["status"]), event.get("message", "")))
                except (ValueError, KeyError, TypeError):
                    logger.debug("Capture worker: %s", line.rstrip())
            returncode = self._process.wait()
            if not self._stop_event.is_set():
                self.report(Result(Status.UNAVAILABLE, "Captura pausada. Verifique o driver e as permissões da sessão."))
            if returncode and not self._stop_event.is_set():
                logger.error(
                    "Clipboard listener exited (%s). Capture is paused; "
                    "no focus-stealing polling fallback will be used.", returncode,
                )
        except OSError as exc:
            self.report(Result(Status.UNAVAILABLE, f"Captura indisponível: {exc}"))
            logger.error("Cannot start clipboard listener: %s", exc)
        finally:
            self.running = False
            if self._process is not None and self._process.stdout is not None:
                self._process.stdout.close()

    def start_background(self):
        """Start the listener thread if it is not already running.

        The stop event is cleared before the daemon thread starts, so a stopped
        daemon can be restarted. Calling this method while the thread is alive
        has no effect.
        """
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the listener subprocess, thread, and driver observation.

        The subprocess is terminated and killed if it does not exit within two
        seconds. The daemon thread is joined for up to two seconds. Driver
        observation is stopped after the subprocess and thread are handled.
        """
        self._stop_event.set()
        with self._process_lock:
            process = self._process
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        self.driver.stop_observation()
        self.running = False
        logger.info("ClipX Clipboard Daemon stopped.")


@registered_process()
def run_standalone_daemon():
    """Run the clipboard daemon until a termination signal arrives.

    SIGINT and SIGTERM are converted into a clean daemon stop followed by
    ``sys.exit(0)``. The main thread waits for the listener thread in short
    intervals and always stops the daemon on exit.
    """
    daemon = ClipboardDaemon()

    def handle_signal(sig, frame):
        """Stop the daemon and exit after a termination signal.

        Args:
            sig (int): Received signal number.
            frame: Current stack frame supplied by the signal module.
        """
        logger.info("Received termination signal, shutting down...")
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    # Keep signal handling outside the listener's process-creation lock.
    daemon.start_background()
    try:
        while daemon._thread.is_alive():
            daemon._thread.join(timeout=0.25)
    finally:
        daemon.stop()


if __name__ == "__main__":
    run_standalone_daemon()
