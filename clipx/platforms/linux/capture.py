"""XFixes listener; the requestor is never mapped or focused."""
import select
import signal
import threading

def watch_x11(capture):
    import json
    from .clipboard import LinuxClipboardDriver
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    driver = LinuxClipboardDriver()
    def report(result):
        print(json.dumps({"status": result.status, "message": result.message}), flush=True)
    try:
        driver.start_observation(capture, stopped, report)
    finally:
        driver.stop_observation()
    return 0


class X11ClipboardListener:
    def __init__(self, capture, selection="CLIPBOARD"):
        from Xlib import X, display
        from Xlib.ext import xfixes

        self.capture = capture
        self.display = display.Display()
        if not self.display.has_extension("XFIXES"):
            self.display.close()
            raise RuntimeError("XFixes clipboard notifications are unavailable")
        self.display.xfixes_query_version()
        # An unmapped InputOnly requestor cannot appear in the taskbar or take focus.
        self.window = self.display.screen().root.create_window(
            0, 0, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
            override_redirect=True, event_mask=X.PropertyChangeMask,
        )
        self.clipboard = self.display.intern_atom(selection)
        self.utf8 = self.display.intern_atom("UTF8_STRING")
        self.string = self.display.intern_atom("STRING")
        self.property = self.display.intern_atom("CLIPX_CLIPBOARD")
        self.incr = self.display.intern_atom("INCR")
        self.target = self.utf8
        self.timestamp = X.CurrentTime
        self.chunks = None
        self.display.xfixes_select_selection_input(
            self.window, self.clipboard,
            xfixes.XFixesSetSelectionOwnerNotifyMask
            | xfixes.XFixesSelectionWindowDestroyNotifyMask
            | xfixes.XFixesSelectionClientCloseNotifyMask,
        )
        self.request_content()

    def request_content(self, target=None, timestamp=0):
        self.target = target or self.utf8
        self.timestamp = timestamp
        self.chunks = None
        self.window.delete_property(self.property)
        self.window.convert_selection(
            self.clipboard, self.target, self.property, timestamp,
        )
        self.display.flush()

    def handle_event(self, event):
        from Xlib import X
        from Xlib.ext import xfixes

        if isinstance(event, xfixes.SelectionNotify):
            if event.owner:
                self.request_content(timestamp=event.selection_timestamp)
            else:
                self.chunks = None
                self.capture.save("")
        elif event.type == X.SelectionNotify:
            if event.selection != self.clipboard or event.target != self.target:
                return
            if self.timestamp and event.time != self.timestamp:
                return
            if event.property == X.NONE:
                if self.target == self.utf8:
                    self.request_content(self.string, self.timestamp)
                else:
                    self.capture.save("")
                return
            value = self.window.get_full_property(self.property, X.AnyPropertyType)
            if value is not None:
                if value.property_type == self.incr:
                    self.chunks = bytearray()
                elif value.format == 8:
                    self.save_bytes(bytes(value.value))
            self.window.delete_property(self.property)
            self.display.flush()
        elif (
            event.type == X.PropertyNotify
            and event.atom == self.property
            and event.state == X.PropertyNewValue
            and self.chunks is not None
        ):
            value = self.window.get_full_property(self.property, X.AnyPropertyType)
            if value is not None and value.format == 8:
                data = bytes(value.value)
                if data:
                    self.chunks.extend(data)
                else:
                    self.save_bytes(bytes(self.chunks))
                    self.chunks = None
            self.window.delete_property(self.property)
            self.display.flush()

    def save_bytes(self, data):
        encoding = "utf-8" if self.target == self.utf8 else "latin-1"
        self.capture.save(data.decode(encoding, errors="replace"))

    def run(self, stopped):
        while not stopped.is_set():
            if self.display.pending_events():
                self.handle_event(self.display.next_event())
            else:
                # Wait for X events; the timeout only lets termination signals run.
                select.select([self.display.fileno()], [], [], 0.25)

    def close(self):
        self.window.destroy()
        self.display.close()


