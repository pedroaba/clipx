"""Clipboard capture, Linux listener selection and X11 integration behavior."""
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

from clipx.capture import ClipboardCapture
from clipx.platforms.linux.capture import X11ClipboardListener
from clipx.platforms.linux.clipboard import LinuxClipboardDriver
from clipx.daemon import ClipboardDaemon
from clipx.storage import Storage


class CaptureTests(unittest.TestCase):
    """Exercise capture deduplication and daemon listener lifecycle."""

    def setUp(self):
        """Create an isolated temporary storage for each test."""
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = Storage(Path(self.temp.name) / "history.db")

    def test_capture_preserves_text_and_deduplicates_notifications(self):
        """Repeated and empty notifications are skipped while new text is stored verbatim."""
        capture = ClipboardCapture(self.storage)
        with patch.object(self.storage, "add_clip", wraps=self.storage.add_clip) as add:
            capture.save("first\nsecond\n")
            capture.save("first\nsecond\n")
            self.assertEqual(add.call_count, 1)
            capture.save("")
            capture.save("first\nsecond\n")
            self.assertEqual(add.call_count, 2)
        self.assertEqual(self.storage.get_clips()[0].content, "first\nsecond\n")

    def test_xwayland_uses_one_listener_and_no_wl_paste(self):
        """With an X display the daemon starts one X11 watcher and stops when it exits."""
        daemon = ClipboardDaemon(self.storage, driver=LinuxClipboardDriver())
        with patch.dict(os.environ, {"DISPLAY": ":0"}):
            command = daemon.listener_command()
        self.assertEqual(command[-1], "--watch-x11")
        self.assertNotIn("wl-paste", command)
        process = Mock()
        process.wait.return_value = 1
        process.stdout = Mock()
        process.stdout.__iter__ = Mock(return_value=iter(()))
        with patch("clipx.daemon.subprocess.Popen", return_value=process) as start:
            daemon.run_loop()
        start.assert_called_once()
        self.assertFalse(daemon.running)

    def test_wayland_without_x11_uses_only_watch(self):
        """Without an X display the listener command relies solely on wl-paste --watch."""
        with patch.dict(os.environ, {"DISPLAY": ""}):
            command = ClipboardDaemon(self.storage, driver=LinuxClipboardDriver()).listener_command()
        self.assertEqual(command[:4], ["wl-paste", "--type", "text", "--watch"])
        self.assertIn("clipx.capture", command)

    def test_stop_terminates_listener_and_cancels_pending_start(self):
        """Stopping terminates a running listener and prevents a later run loop from starting."""
        daemon = ClipboardDaemon(self.storage, driver=LinuxClipboardDriver())
        process = Mock()
        process.poll.return_value = None
        daemon._process = process
        daemon.stop()
        process.terminate.assert_called_once()
        with patch("clipx.daemon.subprocess.Popen") as start:
            daemon.run_loop()
        start.assert_not_called()


@unittest.skipUnless(os.environ.get("CLIPX_TEST_X11"), "requires an X11 connection")
class X11IntegrationTests(unittest.TestCase):
    """Opt-in checks against a real X server using a private selection."""

    def test_event_capture_without_mapping_windows_or_changing_user_clipboard(self):
        """Capture a private selection without mapping windows or touching CLIPBOARD."""
        from Xlib import X, display, protocol
        from uuid import uuid4

        # A private selection exercises real XFixes events without touching CLIPBOARD.
        selection = "CLIPX_TEST_" + uuid4().hex
        captured = []
        sink = Mock()
        sink.save.side_effect = captured.append
        listener = X11ClipboardListener(sink, selection=selection)
        self.addCleanup(listener.close)
        self.assertEqual(listener.window.get_attributes().map_state, X.IsUnmapped)
        owner = display.Display()
        self.addCleanup(owner.close)
        window = owner.screen().root.create_window(
            0, 0, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
            override_redirect=True,
        )
        self.addCleanup(window.destroy)
        window.set_selection_owner(owner.intern_atom(selection), X.CurrentTime)
        owner.flush()
        text = "Clipboard test\nacentuação & conteúdo completo\n"
        stopped = threading.Event()
        errors = []

        def run_listener():
            """Run the listener until it stops, capturing any raised exception."""
            try:
                listener.run(stopped)
            except Exception as exc:
                errors.append(exc)

        worker = threading.Thread(target=run_listener)
        worker.start()
        try:
            import select
            import time

            deadline = time.monotonic() + 3
            while text not in captured and time.monotonic() < deadline:
                if not owner.pending_events():
                    select.select([owner.fileno()], [], [], 0.05)
                    continue
                event = owner.next_event()
                if event.type == X.SelectionRequest:
                    event.requestor.change_property(
                        event.property, event.target, 8, text.encode("utf-8"),
                    )
                    event.requestor.send_event(protocol.event.SelectionNotify(
                        time=event.time, requestor=event.requestor,
                        selection=event.selection, target=event.target,
                        property=event.property,
                    ))
                    owner.flush()
            self.assertFalse(errors)
            self.assertIn(text, captured)
            self.assertEqual(listener.window.get_attributes().map_state, X.IsUnmapped)
            self.assertEqual(window.get_attributes().map_state, X.IsUnmapped)
        finally:
            stopped.set()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
