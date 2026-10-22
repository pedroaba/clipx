"""Desktop activation for an explicit request to open ClipX."""

import logging
import os
import select
import time
import uuid


def startup_message(token, timestamp, screen):
    """Build a ``_NET_STARTUP_INFO`` payload for a desktop launch.

    Args:
        token (str): Startup notification identifier.
        timestamp (int): X server timestamp of the launch.
        screen (int): Screen number where the window should appear.

    Returns:
        bytes: NUL-terminated UTF-8 message ready to be sent in 20-byte
            client-message chunks.
    """
    return (f'new: ID="{token}" NAME="ClipX" SCREEN={screen} '
            f'TIMESTAMP={timestamp} BIN="clipx" APPLICATION_ID="clipx.desktop"\0').encode("utf-8")


def x11_startup_token():
    """Announce a launch via XWayland when a GNOME custom shortcut has no token.

    The startup-notification protocol also covers activating existing windows.
    Its requestor stays unmapped and never takes focus itself.

    The timestamp is obtained by changing a property on a hidden requestor
    window and waiting up to one second for the resulting ``PropertyNotify``.
    The startup message is then sent to the root window as a sequence of
    ``_NET_STARTUP_INFO_BEGIN``/``_NET_STARTUP_INFO`` client messages. The X
    connection and requestor window are always cleaned up.

    Returns:
        str: Startup notification token of the form
            ``clipx-<pid>-<uuid>_TIME<timestamp>``.

    Raises:
        RuntimeError: If no activation timestamp is received within one second.
    """
    from Xlib import X, Xatom, display, protocol

    connection = display.Display()
    source = None
    try:
        screen = connection.get_default_screen()
        root = connection.screen(screen).root
        source = root.create_window(
            0, 0, 1, 1, 0, 0, X.InputOnly, X.CopyFromParent,
            override_redirect=True, event_mask=X.PropertyChangeMask,
        )
        property_atom = connection.intern_atom("CLIPX_ACTIVATION_TIME")
        source.change_property(property_atom, Xatom.STRING, 8, b"time")
        connection.flush()
        deadline = time.monotonic() + 1
        timestamp = None
        while time.monotonic() < deadline:
            if connection.pending_events():
                event = connection.next_event()
                if event.type == X.PropertyNotify and event.atom == property_atom:
                    timestamp = event.time
                    break
            else:
                select.select([connection.fileno()], [], [], max(0, deadline - time.monotonic()))
        if timestamp is None:
            raise RuntimeError("Could not obtain a desktop activation timestamp")
        token = f"clipx-{os.getpid()}-{uuid.uuid4().hex}_TIME{timestamp}"
        message = startup_message(token, timestamp, screen)
        begin = connection.intern_atom("_NET_STARTUP_INFO_BEGIN")
        continuation = connection.intern_atom("_NET_STARTUP_INFO")
        for offset in range(0, len(message), 20):
            event = protocol.event.ClientMessage(
                window=source.id,
                client_type=begin if offset == 0 else continuation,
                data=(8, message[offset:offset + 20].ljust(20, b"\0")),
            )
            root.send_event(event, event_mask=X.PropertyChangeMask)
        connection.sync()
        return token
    finally:
        if source is not None:
            source.destroy()
        connection.close()


def activation_token_for_launch():
    """Return the best activation token available for opening a window.

    Existing ``XDG_ACTIVATION_TOKEN`` and ``DESKTOP_STARTUP_ID`` environment
    variables take precedence. Otherwise, when both Wayland and X11 displays are
    present and the active Qt platform is neither ``offscreen`` nor ``minimal``,
    a token is announced through XWayland. Failures from that attempt are
    logged as warnings and treated as "no token".

    Returns:
        str: Activation token, or an empty string when none is available.
    """
    token = os.environ.get("XDG_ACTIVATION_TOKEN") or os.environ.get("DESKTOP_STARTUP_ID")
    if token:
        return token
    if (os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY")
            and os.environ.get("QT_QPA_PLATFORM", "").split(";")[0] not in ("offscreen", "minimal")):
        try:
            return x11_startup_token()
        except Exception as exc:
            logging.getLogger("clipx.activation").warning("Desktop activation unavailable: %s", exc)
    return ""
