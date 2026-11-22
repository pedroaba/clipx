"""Bounded access to the focused window and element through macOS Accessibility."""
import ctypes as C
from weakref import finalize


class AXReference:
    """Own a retained Core Foundation reference returned by Accessibility."""

    def __init__(self, address, release):
        self.address = address
        finalize(self, release, address)


class MacOSFocus:
    """Read and restore focus without exposing raw Core Foundation ownership."""

    WINDOW = 'AXFocusedWindow'
    ELEMENT = 'AXFocusedUIElement'
    _ASCII_ENCODING = 0x0600

    def __init__(self):
        self.lib = C.CDLL('/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices')
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        pointer = C.c_void_p
        signatures = (
            (self.lib, 'AXUIElementCreateApplication', [C.c_int], pointer),
            (self.lib, 'AXUIElementSetMessagingTimeout', [pointer, C.c_float], C.c_int),
            (self.lib, 'AXUIElementCopyAttributeValue', [pointer, pointer, C.POINTER(pointer)], C.c_int),
            (self.lib, 'AXUIElementSetAttributeValue', [pointer, pointer, pointer], C.c_int),
            (self.lib, 'AXUIElementPerformAction', [pointer, pointer], C.c_int),
            (self.cf, 'CFStringCreateWithCString', [pointer, C.c_char_p, C.c_uint32], pointer),
            (self.cf, 'CFEqual', [pointer, pointer], C.c_bool),
            (self.cf, 'CFRelease', [pointer], None),
        )
        for library, name, arguments, result in signatures:
            function = getattr(library, name)
            function.argtypes = arguments
            function.restype = result

        self._attributes = {
            name: AXReference(self.cf.CFStringCreateWithCString(None, name.encode('ascii'), self._ASCII_ENCODING),
                              self.cf.CFRelease)
            for name in (self.WINDOW, self.ELEMENT, 'AXFocused', 'AXRaise')
        }
        self._true = pointer.in_dll(self.cf, 'kCFBooleanTrue')

    def _reference(self, address):
        if not address:
            return None
        reference = AXReference(address, self.cf.CFRelease)
        if self.lib.AXUIElementSetMessagingTimeout(address, .1) != 0:
            return None
        return reference

    def application(self, pid):
        return self._reference(self.lib.AXUIElementCreateApplication(pid))

    def read(self, application, attribute):
        value = C.c_void_p()
        status = self.lib.AXUIElementCopyAttributeValue(
            application.address, self._attributes[attribute].address, C.byref(value))
        return self._reference(value.value) if status == 0 else None

    def same(self, current, expected):
        return current is not None and bool(self.cf.CFEqual(current.address, expected.address))

    def raise_window(self, window):
        self.lib.AXUIElementPerformAction(window.address, self._attributes['AXRaise'].address)

    def focus_element(self, element):
        self.lib.AXUIElementSetAttributeValue(element.address, self._attributes['AXFocused'].address, self._true)
