"""XFixes-based clipboard capture process and its X11 listener.

Runs inside the capture helper process. The listener requests selection
contents from the clipboard owner and forwards decoded text to a capture
sink; its own requestor window is never mapped or focused.
"""
import select
import signal
import threading

def watch_x11(capture):
    """Observe an X11 clipboard and report status as JSON on standard output.

    Installs SIGTERM/SIGINT handlers that set a stop event, creates a Linux
    clipboard driver, and blocks in the driver's observation loop until the
    event is set. Each status report is printed as one JSON object and flushed.
    The driver's observation is always stopped on exit.

    Args:
        capture (object): Capture sink exposing ``save`` and ``storage``.

    Returns:
        int: Process exit status, always ``0`` after a normal observation run.
    """
    import json
    from .clipboard import LinuxClipboardDriver
    stopped = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    driver = LinuxClipboardDriver()
    def report(result):
        """Emit a capture status update as a single JSON line to stdout.

        Args:
            result (Result): Capture status to serialize and print.

        The line is printed and flushed immediately so the parent daemon can read
        it without buffering delays.
        """
        print(json.dumps({"status": result.status, "message": result.message}), flush=True)
    try:
        driver.start_observation(capture, stopped, report)
    finally:
        driver.stop_observation()
    return 0


class X11ClipboardListener:
    """Read clipboard content in a separate X11 process via XFixes.

    Registers for XFixes selection-owner notifications on an unmapped
    ``InputOnly`` window, converts the selection to ``UTF8_STRING`` (falling back
    to ``STRING``), and reassembles ``INCR`` transfers chunk by chunk.

    Attributes:
        capture (object): Capture sink receiving the decoded text.
        display (Xlib.display.Display): Connection to the X server.
        window (Xlib.xobject.drawable.Window): Hidden requestor window.
        clipboard (int): Atom of the observed selection.
        utf8 (int): Atom for ``UTF8_STRING``.
        string (int): Atom for the legacy ``STRING`` target.
        property (int): Private property used for transfer data.
        incr (int): Atom marking an incremental transfer.
        target (int): Target currently requested.
        timestamp (int): X timestamp used to reject stale notifications.
        chunks (bytearray | None): Accumulator for incremental data, or ``None``.
    """

    def __init__(self, capture, selection="CLIPBOARD"):
        """Connect to X11 and start observing a selection.

        Args:
            capture (object): Capture sink exposing ``save(text)``.
            selection (str): Selection name to observe.

        Raises:
            RuntimeError: If the X server connection lacks the XFIXES
                extension.
        """
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
        """Ask the selection owner to convert the selection into a property.

        Resets chunk accumulation and deletes the private property before
        issuing the conversion request and flushing the connection.

        Args:
            target (int | None): Atom to request; defaults to ``UTF8_STRING``.
            timestamp (int): X timestamp for the conversion; ``0`` means
                ``CurrentTime``.
        """
        self.target = target or self.utf8
        self.timestamp = timestamp
        self.chunks = None
        self.window.delete_property(self.property)
        self.window.convert_selection(
            self.clipboard, self.target, self.property, timestamp,
        )
        self.display.flush()

    def handle_event(self, event):
        """Process one X event from the listener connection.
        XFixes owner changes trigger a new request, or clear the capture when no
        owner remains. Selection replies are ignored when they address another
        selection, target, or stale timestamp; a missing property falls back
        from ``UTF8_STRING`` to ``STRING``, or clears the capture. Incremental
        transfers accumulate ``PropertyNewValue`` chunks until an empty chunk
        terminates them.

        Args:
            event (Xlib.protocol.event.Event): Event returned by the X
                connection.
        """
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
        """Decode raw clipboard bytes and forward them to the capture sink.

        Bytes are decoded as UTF-8 for ``UTF8_STRING`` and as Latin-1 for the
        legacy ``STRING`` target, replacing undecodable sequences.

        Args:
            data (bytes): Raw selection data.
        """
        encoding = "utf-8" if self.target == self.utf8 else "latin-1"
        self.capture.save(data.decode(encoding, errors="replace"))

    def run(self, stopped):
        """Dispatch X events until the stop event is set.

        When no events are pending, waits up to 0.25 seconds on the X
        connection file descriptor so that termination signals can be handled.

        Args:
            stopped (threading.Event): Event that ends the loop when set.
        """
        while not stopped.is_set():
            if self.display.pending_events():
                self.handle_event(self.display.next_event())
            else:
                # Wait for X events; the timeout only lets termination signals run.
                select.select([self.display.fileno()], [], [], 0.25)

    def close(self):
        """Destroy the hidden requestor window and close the X connection."""
        self.window.destroy()
        self.display.close()


