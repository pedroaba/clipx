"""A sequence of keyboard keys, rendered using reusable Keycap atoms."""
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLabel, QSizePolicy
from clipx.ui.atoms.keycap import Keycap


def key_parts(sequence):
    sequence = QKeySequence(sequence)
    if sequence.isEmpty():
        return []
    combo = sequence[0]
    labels = ('⌘', '⌥', '⇧', '⌃') if sys.platform == 'darwin' else ('Ctrl', 'Alt', 'Shift', 'Super')
    parts = [label for flag, label in zip((Qt.KeyboardModifier.ControlModifier,
        Qt.KeyboardModifier.AltModifier, Qt.KeyboardModifier.ShiftModifier,
        Qt.KeyboardModifier.MetaModifier), labels) if combo.keyboardModifiers() & flag]
    key = combo.key()
    text = {Qt.Key.Key_Return: '↵', Qt.Key.Key_Enter: '↵', Qt.Key.Key_Escape: 'Esc',
            Qt.Key.Key_Delete: '⌦' if sys.platform == 'darwin' else 'Del',
            Qt.Key.Key_Backspace: '⌫', Qt.Key.Key_Up: '↑', Qt.Key.Key_Down: '↓',
            Qt.Key.Key_Left: '←', Qt.Key.Key_Right: '→', Qt.Key.Key_Tab: '⇥',
            Qt.Key.Key_Space: 'Space'}.get(key)
    parts.append(text or QKeySequence(key.value).toString(QKeySequence.SequenceFormat.NativeText))
    return parts


class ShortcutKeycaps(QWidget):
    def __init__(self, sequence='', parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.box = QHBoxLayout(self)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(5)
        self.caps = []
        self.set_sequence(sequence)

    def _clear(self):
        while self.box.count():
            widget = self.box.takeAt(0).widget()
            if widget:
                widget.hide()
                widget.deleteLater()
        self.caps = []

    def set_sequence(self, sequence):
        self._clear()
        for part in key_parts(sequence):
            cap = Keycap(part)
            self.caps.append(cap)
            self.box.addWidget(cap)

    def set_message(self, text):
        self._clear()
        label = QLabel(text)
        label.setObjectName('RecorderMessage')
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.box.addWidget(label)
