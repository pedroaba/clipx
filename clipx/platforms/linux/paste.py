"""Send the paste shortcut through a private Linux uinput keyboard."""
import fcntl
import logging
import os
import struct
import threading
import time

logger = logging.getLogger('clipx.desktop')

# linux/uinput.h ioctl requests on Linux amd64 and arm64.
_UI_DEV_CREATE = 0x5501
_UI_DEV_DESTROY = 0x5502
_UI_DEV_SETUP = 0x405C5503
_UI_SET_EVBIT = 0x40045564
_UI_SET_KEYBIT = 0x40045565
_BUS_VIRTUAL = 0x06
_EV_KEY = 1
_KEY_LEFTCTRL = 29
_KEY_V = 47

# udev's input_id expects key codes 1–31 to classify a device as a keyboard.
# Only the keys in _PASTE_EVENTS are ever sent.
_KEYBOARD_KEYS = (*range(1, 32), _KEY_V)
_SETUP = struct.pack('@HHHH80sI', _BUS_VIRTUAL, 0, 0, 1, b'ClipX Paste Keyboard', 0)
_EVENT = struct.Struct('@llHHi')
_SYNC_REPORT = _EVENT.pack(0, 0, 0, 0, 0)
_PASTE_EVENTS = b''.join(
    _EVENT.pack(0, 0, _EV_KEY, key, value) + _SYNC_REPORT
    for key, value in ((_KEY_LEFTCTRL, 1), (_KEY_V, 1), (_KEY_V, 0), (_KEY_LEFTCTRL, 0))
)


class PasteKeyboard:
    """Keep one virtual keyboard alive for the desktop driver's lifetime."""

    def __init__(self):
        self._lock = threading.Lock()
        self._fd = None
        self._ready_at = 0.0
        self._closed = False

    def paste(self, cancelled: threading.Event) -> bool:
        """Submit Ctrl+V in one write once the compositor can see the device."""
        with self._lock:
            if self._closed or cancelled.is_set():
                return False
            try:
                if self._fd is None:
                    self._create_device()
                if cancelled.wait(max(0, self._ready_at - time.monotonic())):
                    return False
                if os.write(self._fd, _PASTE_EVENTS) != len(_PASTE_EVENTS):
                    raise OSError('incomplete keyboard event write')
                return True
            except OSError as exc:
                logger.warning('Automatic paste via /dev/uinput failed: %s', exc)
                self._destroy_device()
                return False

    def _create_device(self):
        fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(fd, _UI_SET_EVBIT, _EV_KEY)
            for key in _KEYBOARD_KEYS:
                fcntl.ioctl(fd, _UI_SET_KEYBIT, key)
            fcntl.ioctl(fd, _UI_DEV_SETUP, _SETUP)
            fcntl.ioctl(fd, _UI_DEV_CREATE)
        except OSError:
            os.close(fd)
            raise
        self._fd = fd
        # Device discovery is asynchronous. Subsequent requests reuse the device.
        self._ready_at = time.monotonic() + 1.0

    def _destroy_device(self):
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            fcntl.ioctl(fd, _UI_DEV_DESTROY)
        except OSError as exc:
            logger.warning('Could not destroy ClipX virtual keyboard: %s', exc)
        finally:
            os.close(fd)

    def close(self):
        """Close the device and prevent pending workers from reopening it."""
        with self._lock:
            self._closed = True
            self._destroy_device()
