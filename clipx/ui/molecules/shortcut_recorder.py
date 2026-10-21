"""An explicit click-to-record control, with no native text editor underneath."""

import sys

from PyQt6.QtCore import QEvent, Qt, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QPainter
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QStyleOptionButton, QStyle, QSizePolicy
from clipx.ui.molecules.keycaps import ShortcutKeycaps

from clipx.shortcuts import normalize


def display_shortcut(sequence):
    sequence = QKeySequence(sequence)
    if sequence.isEmpty():
        return "Desativado"
    if sys.platform == "darwin":
        return sequence.toString(QKeySequence.SequenceFormat.NativeText)
    combination = sequence[0]
    parts = [name for flag, name in (
        (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
        (Qt.KeyboardModifier.AltModifier, "Alt"),
        (Qt.KeyboardModifier.ShiftModifier, "Shift"),
        (Qt.KeyboardModifier.MetaModifier, "Super"),
    ) if combination.keyboardModifiers() & flag]
    text = QKeySequence(combination.key().value).toString(QKeySequence.SequenceFormat.NativeText)
    names = {"Meta": "Super", "Return": "Enter", "Esc": "Esc", "Space": "Espaço",
             "Up": "↑", "Down": "↓", "Left": "←", "Right": "→"}
    return " + ".join([*parts, names.get(text, text)])


class ShortcutRecorder(QPushButton):
    recordingRequested = pyqtSignal()
    recordingCancelled = pyqtSignal()
    sequenceRecorded = pyqtSignal(str)
    sequence_changed = pyqtSignal()

    def __init__(self, sequence="", parent=None):
        super().__init__(parent)
        self.recording = False
        self._sequence = QKeySequence(sequence)
        self.setObjectName("ShortcutRecorder")
        self.setMinimumSize(96, 36)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self.keycaps = ShortcutKeycaps(parent=self)
        box = QHBoxLayout(self)
        box.setContentsMargins(6, 3, 6, 3)
        box.addStretch()
        box.addWidget(self.keycaps)
        box.addStretch()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.clicked.connect(self.recordingRequested)
        self.setKeySequence(self._sequence)
        self.setToolTip("Clique para gravar uma combinação. Esc cancela a gravação.")

    def keySequence(self):
        return QKeySequence(self._sequence)

    def setKeySequence(self, sequence):
        changed = self._sequence != QKeySequence(sequence)
        self._sequence = QKeySequence(sequence)
        if not self.recording:
            self.setText(display_shortcut(self._sequence) if not self._sequence.isEmpty() else "Definir atalho")
            self.keycaps.set_sequence(self._sequence)
            if self._sequence.isEmpty():
                self.keycaps.set_message("Definir atalho")
        self.setAccessibleName("Atalho: " + display_shortcut(self._sequence))
        self.updateGeometry()
        if changed:
            self.sequence_changed.emit()

    def setText(self, text):
        super().setText(text)
        if hasattr(self, 'keycaps'):
            self.keycaps.set_message(text)
            self.updateGeometry()

    def sizeHint(self):
        if not hasattr(self, 'keycaps'):
            return super().sizeHint()
        return QSize(max(96, self.keycaps.sizeHint().width() + 16), 36)

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''  # Keycap atoms render the sequence instead of the button label.
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)

    def clear(self):
        self.setKeySequence(QKeySequence())

    def start_recording(self):
        self.recording = True
        self.setProperty("recording", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("Pressione a combinação…")
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def stop_recording(self):
        self.recording = False
        self.setProperty("recording", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setKeySequence(self._sequence)

    def event(self, event):
        # Capture Tab/Enter as keys instead of navigating or activating dialog buttons.
        if self.recording and event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if self.recording and event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if not self.recording:
            return super().keyPressEvent(event)
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.recordingCancelled.emit()
            return
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
            flags = event.modifiers()
            for key, flag in ((Qt.Key.Key_Control, Qt.KeyboardModifier.ControlModifier),
                              (Qt.Key.Key_Alt, Qt.KeyboardModifier.AltModifier),
                              (Qt.Key.Key_Shift, Qt.KeyboardModifier.ShiftModifier),
                              (Qt.Key.Key_Meta, Qt.KeyboardModifier.MetaModifier)):
                if event.key() == key:
                    flags |= flag
            parts = [label for flag, label in (
                (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                (Qt.KeyboardModifier.AltModifier, "Alt"),
                (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                (Qt.KeyboardModifier.MetaModifier, "Super"),
            ) if flags & flag]
            if sys.platform == "darwin":
                parts = [symbol for flag, symbol in ((Qt.KeyboardModifier.ControlModifier, "⌘"),
                         (Qt.KeyboardModifier.AltModifier, "⌥"), (Qt.KeyboardModifier.ShiftModifier, "⇧"),
                         (Qt.KeyboardModifier.MetaModifier, "⌃")) if flags & flag]
            self.setText(" + ".join([*parts, "…"]))
            return
        try:
            sequence = normalize(QKeySequence(event.keyCombination()))
        except ValueError:
            return
        self.sequenceRecorded.emit(sequence)

    def focusOutEvent(self, event):
        if self.recording:
            self.recordingCancelled.emit()
        super().focusOutEvent(event)
