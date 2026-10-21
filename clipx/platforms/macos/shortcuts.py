"""macOS hotkeys: Carbon registers one combination, without a keyboard tap."""
import ctypes as C
import json
from pathlib import Path
import tempfile
import os

from PyQt6.QtCore import QObject, pyqtSignal, Qt
from PyQt6.QtGui import QKeySequence
from clipx.shortcuts import normalize


class EventType(C.Structure):
    _fields_ = [('eventClass', C.c_uint32), ('eventKind', C.c_uint32)]


class HotKeyID(C.Structure):
    _fields_ = [('signature', C.c_uint32), ('id', C.c_uint32)]


class CarbonHotKeys:
    SIGNATURE = int.from_bytes(b'CLPX', 'big')
    KEYS = {'A': 0, 'S': 1, 'D': 2, 'F': 3, 'H': 4, 'G': 5, 'Z': 6, 'X': 7,
            'C': 8, 'V': 9, 'B': 11, 'Q': 12, 'W': 13, 'E': 14, 'R': 15,
            'Y': 16, 'T': 17, '1': 18, '2': 19, '3': 20, '4': 21, '6': 22,
            '5': 23, '=': 24, '9': 25, '7': 26, '-': 27, '8': 28, '0': 29,
            ']': 30, 'O': 31, 'U': 32, '[': 33, 'I': 34, 'P': 35, ',': 43,
            '/': 44, 'N': 45, 'M': 46, '.': 47, ';': 41, "'": 39, '\\': 42, '`': 50}
    KEYS.update({'Return': 36, 'L': 37, 'J': 38, 'K': 40, 'Space': 49, 'Tab': 48,
                 'Esc': 53, 'Backspace': 51, 'Del': 117, 'Left': 123, 'Right': 124,
                 'Down': 125, 'Up': 126, 'Home': 115, 'End': 119, 'PgUp': 116, 'PgDown': 121,
                 'F1': 122, 'F2': 120, 'F3': 99, 'F4': 118, 'F5': 96, 'F6': 97,
                 'F7': 98, 'F8': 100, 'F9': 101, 'F10': 109, 'F11': 103, 'F12': 111})

    def __init__(self):
        self.lib = C.CDLL('/System/Library/Frameworks/Carbon.framework/Carbon')
        self.lib.RegisterEventHotKey.argtypes = [C.c_uint32, C.c_uint32, HotKeyID, C.c_void_p,
                                                  C.c_uint32, C.POINTER(C.c_void_p)]
        self.lib.RegisterEventHotKey.restype = C.c_int32
        self.lib.UnregisterEventHotKey.argtypes = [C.c_void_p]
        self.lib.UnregisterEventHotKey.restype = C.c_int32
        self.lib.GetApplicationEventTarget.restype = C.c_void_p
        self.lib.GetEventParameter.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.c_void_p,
                                               C.c_uint32, C.c_void_p, C.c_void_p]
        self.lib.GetEventParameter.restype = C.c_int32
        self.lib.InstallEventHandler.argtypes = [C.c_void_p, C.c_void_p, C.c_uint32,
                                                 C.POINTER(EventType), C.c_void_p, C.POINTER(C.c_void_p)]
        self.lib.InstallEventHandler.restype = C.c_int32
        self.lib.RemoveEventHandler.argtypes = [C.c_void_p]
        self.callbacks = {}
        self.next_id = 0
        self.handler_ref = C.c_void_p()
        self.handler = C.CFUNCTYPE(C.c_int32, C.c_void_p, C.c_void_p, C.c_void_p)(self._receive)
        event = EventType(int.from_bytes(b'keyb', 'big'), 6)
        status = self.lib.InstallEventHandler(self.lib.GetApplicationEventTarget(), self.handler,
                                              1, C.byref(event), None, C.byref(self.handler_ref))
        if status:
            raise RuntimeError(f'Não foi possível preparar o atalho global ({status}).')

    def _receive(self, handler, event, data):
        identity = HotKeyID()
        status = self.lib.GetEventParameter(event, int.from_bytes(b'----', 'big'),
                    int.from_bytes(b'hkid', 'big'), None, C.sizeof(identity), None, C.byref(identity))
        if status == 0 and identity.signature == self.SIGNATURE:
            callback = self.callbacks.get(identity.id)
            if callback:
                callback()
                return 0
        return -9874  # eventNotHandledErr

    def combination(self, sequence):
        combo = QKeySequence(normalize(sequence))[0]
        key = QKeySequence(combo.key().value).toString(QKeySequence.SequenceFormat.PortableText)
        code = self.KEYS.get(key)
        if code is None:
            raise ValueError('Tecla não suportada no atalho macOS. Use letras, números, navegação ou F1–F12.')
        # Qt swaps Control/Meta on macOS: portable Ctrl is native Command.
        modifiers = 0
        for flag, native in ((Qt.KeyboardModifier.ControlModifier, 1 << 8),
                             (Qt.KeyboardModifier.MetaModifier, 1 << 12),
                             (Qt.KeyboardModifier.AltModifier, 1 << 11),
                             (Qt.KeyboardModifier.ShiftModifier, 1 << 9)):
            if combo.keyboardModifiers() & flag:
                modifiers |= native
        if not modifiers & ((1 << 8) | (1 << 12) | (1 << 11)):
            raise ValueError('Use Command, Control ou Option no atalho global.')
        return code, modifiers

    def register(self, sequence, callback):
        code, modifiers = self.combination(sequence)
        self.next_id += 1
        identity = HotKeyID(self.SIGNATURE, self.next_id)
        reference = C.c_void_p()
        status = self.lib.RegisterEventHotKey(code, modifiers, identity,
                        self.lib.GetApplicationEventTarget(), 0, C.byref(reference))
        if status:
            raise RuntimeError(f'Não foi possível registrar o atalho ({status}). Escolha outra combinação.')
        self.callbacks[self.next_id] = callback
        return (reference, self.next_id)

    def unregister(self, handle):
        reference, identity = handle
        self.lib.UnregisterEventHotKey(reference)
        self.callbacks.pop(identity, None)

    def close(self):
        if self.handler_ref:
            self.lib.RemoveEventHandler(self.handler_ref)
            self.handler_ref = C.c_void_p()


class MacOSGlobalShortcut(QObject):
    activated = pyqtSignal()
    default_sequence = 'Ctrl+Shift+V'  # Qt portable representation of ⌘⇧V.
    portable_bindings = True
    modifier_hint = '⌘ Command · ⌥ Option · ⌃ Control · Esc cancela a gravação'

    @staticmethod
    def to_binding(sequence):
        if not sequence:
            return ''
        CarbonHotKeys.combination(CarbonHotKeys.__new__(CarbonHotKeys), sequence)
        return normalize(sequence)

    @staticmethod
    def from_binding(binding):
        return normalize(binding) if binding else ''


    def __init__(self, path=None, native=None):
        super().__init__()
        from clipx.platforms.paths import PlatformPaths
        self.path = Path(path) if path else PlatformPaths('darwin').config / 'settings.json'
        self.native = native
        self.handle = None
        self.callback = None
        self.paused = False
        self._value = self.default_sequence
        try:
            data = json.loads(self.path.read_text())
            value = data.get('global_shortcut', self.default_sequence)
            self._value = normalize(value) if value else ''
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    def read(self):
        return self._value

    def start(self, callback):
        if self.callback is not None:
            return
        if self.native is None:
            self.native = CarbonHotKeys()
        self.callback = callback
        self.activated.connect(callback, Qt.ConnectionType.QueuedConnection)
        try:
            if self._value:
                self.handle = self.native.register(self._value, self.activated.emit)
        except Exception:
            # Keep the receiver ready so Preferences can replace a conflicting default.
            # No hotkey is active yet, and stop() still releases the event handler.
            raise

    def _persist(self, sequence):
        data = {}
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                data = {}
        except (OSError, ValueError):
            pass
        data['global_shortcut'] = sequence
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, name = tempfile.mkstemp(dir=self.path.parent, prefix='.settings-')
        try:
            with os.fdopen(handle, 'w') as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write('\n')
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)

    def write(self, sequence):
        value = normalize(sequence) if sequence else ''
        if value == self._value:
            return
        if self.paused:
            raise RuntimeError('Termine a gravação antes de aplicar o atalho.')
        if self.native is None or self.callback is None:
            raise RuntimeError('Atalho global não foi iniciado nesta sessão.')
        # Register before releasing the old combination; failures leave it untouched.
        new_handle = self.native.register(value, self.activated.emit) if value else None
        try:
            self._persist(value)
        except Exception:
            if new_handle is not None:
                self.native.unregister(new_handle)
            raise
        if self.handle is not None:
            self.native.unregister(self.handle)
        self.handle = new_handle
        self._value = value

    def conflicts(self, sequence):
        # Carbon is authoritative at registration; macOS exposes no GNOME-style inventory.
        return []

    def pause(self):
        value = self._value
        if self.handle is not None:
            self.native.unregister(self.handle)
            self.handle = None
        self.paused = True
        return value

    def resume(self, sequence):
        if self.paused and self.callback is not None and self._value:
            self.handle = self.native.register(self._value, self.activated.emit)
        self.paused = False

    def recover(self):
        pass  # Carbon registrations are process-owned and released by the OS on exit.

    def stop(self):
        if self.handle is not None:
            self.native.unregister(self.handle)
            self.handle = None
        if self.callback is not None:
            self.activated.disconnect(self.callback)
            self.callback = None
        if self.native is not None:
            self.native.close()
        self.paused = False
