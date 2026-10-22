"""Shared text ingestion and native capture worker entrypoint.

``ClipboardCapture`` deduplicates and persists text, while ``main`` provides the
worker command invoked by platform clipboard drivers or directly from stdin.
"""

import argparse
import logging
import os
from pathlib import Path
import signal
import sys

from clipx.detector import ContentDetector
from clipx.storage import Storage

logger = logging.getLogger("clipx.capture")


class ClipboardCapture:
    """Persist clipboard text while suppressing consecutive duplicates.

    The capture keeps the hash of the last saved content so repeated listener
    events for the same text do not create extra history updates.
    """

    def __init__(self, storage):
        """Initialize a capture bound to a storage backend.

        Args:
            storage (Storage): Storage that receives detected clipboard items.
        """
        self.storage = storage
        self._last_hash = None

    def reset(self):
        """Forget the last saved content hash.

        Resetting allows the same text to be saved again after a clear or
        sensitive clipboard event.
        """
        self._last_hash = None

    def save(self, text):
        """Detect and persist clipboard text unless it is blank or repeated.

        Blank or whitespace-only text clears the duplicate state. Content whose
        SHA-256 hash matches the previous save is ignored. Otherwise the content
        type and language are detected and the clip is written to storage.

        Args:
            text (str): Clipboard text to store.
        """
        if not text or not text.strip():
            self._last_hash = None
            return
        content_hash = Storage.compute_hash(text)
        if content_hash == self._last_hash:
            return
        detection = ContentDetector.detect(text)
        self.storage.add_clip(text, detection.clip_type, detection.language)
        self._last_hash = content_hash



def main():
    """Run the capture worker selected by command-line flags.

    The worker accepts a database path. ``--watch-x11`` delegates to the Linux
    X11 watcher, ``--watch-macos`` observes the native pasteboard until SIGINT
    or SIGTERM, and the default mode reads one clip from stdin unless
    ``CLIPBOARD_STATE`` marks the clipboard as nil, clear, or sensitive. macOS
    mode prints JSON status lines to stdout for the supervising daemon.

    Returns:
        int: Exit code returned by the X11 watcher in that mode, or zero
            otherwise.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--watch-x11", action="store_true")
    parser.add_argument("--watch-macos", action="store_true")
    args = parser.parse_args()
    capture = ClipboardCapture(Storage(args.database))
    if args.watch_x11:
        from clipx.platforms.linux.capture import watch_x11
        return watch_x11(capture)
    if args.watch_macos:
        import json
        import threading
        from clipx.platforms.macos.clipboard import MacOSClipboardDriver
        stopped = threading.Event()
        signal.signal(signal.SIGTERM, lambda *_: stopped.set())
        signal.signal(signal.SIGINT, lambda *_: stopped.set())
        def report(result):
            """Print a capture status as one JSON line for the daemon.

            Args:
                result (Result): Status object with ``status`` and ``message``
                    attributes.
            """
            print(json.dumps({"status": result.status, "message": result.message}), flush=True)
        driver = MacOSClipboardDriver()
        try:
            driver.start_observation(capture, stopped, report)
        finally:
            driver.stop_observation()
        return 0
    if os.environ.get("CLIPBOARD_STATE") not in ("nil", "clear", "sensitive"):
        capture.save(sys.stdin.read())
    return 0


if __name__ == "__main__":
    sys.exit(main())
