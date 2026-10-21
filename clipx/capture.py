"""Shared text ingestion and native capture worker entrypoint."""

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
    def __init__(self, storage):
        self.storage = storage
        self._last_hash = None

    def reset(self):
        self._last_hash = None

    def save(self, text):
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
