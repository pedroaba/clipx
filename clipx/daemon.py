import json
import logging
import os
import signal
import subprocess
import sys
import threading
from typing import Optional

from clipx.storage import Storage
from clipx.platforms import get_platform
from clipx.platforms.base import Result, Status
from PyQt6.QtCore import QObject, pyqtSignal

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("clipx.daemon")


class ClipboardDaemon(QObject):
    status_changed = pyqtSignal(object)
    """Supervise one event listener; never poll with Wayland popup windows."""

    def __init__(self, storage: Optional[Storage] = None, driver=None):
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
        return self.driver.listener_command(self.storage.db_path)

    def report(self, result):
        self.status = result
        self.status_changed.emit(result)

    def run_loop(self):
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
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_loop, daemon=True)
        self._thread.start()

    def stop(self):
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


def run_standalone_daemon():
    daemon = ClipboardDaemon()

    def handle_signal(sig, frame):
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
