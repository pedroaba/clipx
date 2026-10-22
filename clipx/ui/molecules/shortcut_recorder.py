"""An explicit click-to-record control, with no native text editor underneath."""

import sys

from PyQt6.QtCore import QEvent, Qt, pyqtSignal, QSize
from PyQt6.QtGui import QKeySequence, QPainter
from PyQt6.QtWidgets import QPushButton, QHBoxLayout, QStyleOptionButton, QStyle, QSizePolicy
from clipx.ui.molecules.keycaps import ShortcutKeycaps

from clipx.shortcuts import normalize


def display_shortcut(sequence):
    """Format a key sequence for display in the recorder.

    Args:
        sequence (str | QKeySequence): Sequence to format.

    Returns:
        str: ``'Desativado'`` for an empty sequence, native text on macOS, or a
            ``' + '``-joined list of modifier names and a mapped key name.
    """
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
    """Click-to-record shortcut control that renders keycaps instead of text.

    Attributes:
        recordingRequested (pyqtSignal): Emitted when the button is clicked.
        recordingCancelled (pyqtSignal): Emitted on Escape or when focus leaves
            while recording.
        sequenceRecorded (pyqtSignal): Emitted with the normalized combination
            captured from a key press.
        sequence_changed (pyqtSignal): Emitted when :meth:`setKeySequence`
            receives a different sequence.
    """

    recordingRequested = pyqtSignal()
    recordingCancelled = pyqtSignal()
    sequenceRecorded = pyqtSignal(str)
    sequence_changed = pyqtSignal()

    def __init__(self, sequence="", parent=None):
        """Create the recorder with centered keycaps.

        Args:
            sequence (str, optional): Initial key sequence. Defaults to empty.
            parent (QWidget, optional): Parent widget that owns the recorder.
        """
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
        """Return a copy of the current key sequence.

        Returns:
            QKeySequence: The sequence currently stored by the recorder.
        """
        return QKeySequence(self._sequence)

    def setKeySequence(self, sequence):
        """Store a sequence and refresh the display and accessibility name.

        While recording, the visual state is left untouched. When the sequence
        actually changes, ``sequence_changed`` is emitted.

        Args:
            sequence (str | QKeySequence): Sequence to store.
        """
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
        """Set the button text and mirror it in the keycap row.

        Args:
            text (str): Message shown by the button and the keycap row.
        """
        super().setText(text)
        if hasattr(self, 'keycaps'):
            self.keycaps.set_message(text)
            self.updateGeometry()

    def sizeHint(self):
        """Return a size wide enough for the keycaps with minimum padding.

        Returns:
            QSize: Preferred widget size, or the base hint before keycaps exist.
        """
        if not hasattr(self, 'keycaps'):
            return super().sizeHint()
        return QSize(max(96, self.keycaps.sizeHint().width() + 16), 36)

    def paintEvent(self, event):
        """Draw the button chrome without its text label.

        Args:
            event (QPaintEvent): Paint event supplied by Qt.
        """
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = ''  # Keycap atoms render the sequence instead of the button label.
        painter = QPainter(self)
        self.style().drawControl(QStyle.ControlElement.CE_PushButton, option, painter, self)

    def clear(self):
        """Clear the stored sequence and restore the placeholder display."""
        self.setKeySequence(QKeySequence())

    def start_recording(self):
        """Enter recording mode, apply the recording style, and take focus."""
        self.recording = True
        self.setProperty("recording", True)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText("Pressione a combinação…")
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def stop_recording(self):
        """Leave recording mode and repaint the stored sequence."""
        self.recording = False
        self.setProperty("recording", False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setKeySequence(self._sequence)

    def event(self, event):
        """Intercept keys while recording so they are captured, not navigated.

        Args:
            event (QEvent): Event delivered to the widget.

        Returns:
            bool: True when the event was consumed during recording; otherwise
                the base class result.
        """
        # Capture Tab/Enter as keys instead of navigating or activating dialog buttons.
        if self.recording and event.type() == QEvent.Type.ShortcutOverride:
            event.accept()
            return True
        if self.recording and event.type() == QEvent.Type.KeyPress:
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        """Handle a key press during recording.

        Escape emits ``recordingCancelled``. Modifier-only presses update a
        preview message without ending recording. Any other combination is
        normalized and emitted through ``sequenceRecorded``; combinations that
        normalization rejects are ignored. Auto-repeat events are dropped.

        Args:
            event (QKeyEvent): Key event to process.
        """
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
        """Cancel recording when the widget loses focus.

        Args:
            event (QFocusEvent): Focus event forwarded to the base class.
        """
        if self.recording:
            self.recordingCancelled.emit()
        super().focusOutEvent(event)
