"""Choose a global shortcut without pressing a chord intercepted by the desktop."""

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from clipx.ui.templates.window import SystemDialog
from clipx.ui.molecules.select import Select
from clipx.ui.molecules.keycaps import ShortcutKeycaps
from clipx.shortcuts import normalize
from clipx.platforms import get_platform
from clipx.ui.foundations.preferences import PREFERENCES_QSS
from clipx.ui.molecules.shortcut_recorder import display_shortcut


class ShortcutPicker(SystemDialog):
    def __init__(self, sequence, parent=None):
        super().__init__(parent)
        self.validate_sequence = parent.backend.to_binding if parent and hasattr(parent, "backend") else get_platform().shortcuts.to_binding
        self.setWindowTitle("ClipX — Escolher atalho")
        self.setMinimumWidth(580)
        self.resize(640, 590)
        self.setStyleSheet(PREFERENCES_QSS + """
            QDialog, QWidget#PickerContent { background: #161616; }
            QLabel#PickerLabel { color: #A1A1AA; font-size: 12pt; font-weight: 400; padding: 0; }
            QLabel#Heading { font-size: 19pt; }
            QFrame#ShortcutPreview { background: #111111; border: 1px dashed #333337; border-radius: 12px; }
            QFrame#ModifierGroup { background: #111111; border: 1px solid #303034; border-radius: 10px; }
            QPushButton#ModifierChip { background: transparent; border: 1px solid transparent; color: #A1A1AA; padding: 9px 8px; font-size: 11pt; }
            QPushButton#ModifierChip:checked { background: #242424; border-color: #36363B; color: #F4F4F5; }
            QPushButton#ModifierChip:focus { border-color: #A1A1AA; }
            QFrame#ShortcutPreview QLabel#Keycap { background: #242424; border: 1px solid #3B3B3F; border-bottom: 3px solid #3B3B3F; border-radius: 8px; padding: 8px 14px; font-size: 19pt; min-height: 28px; }
            QLabel#PickerWarning { background: #302819; border: 1px solid #766025; border-radius: 8px; color: #F5B82E; padding: 12px; font-size: 11pt; }
            QFrame#PickerFooter { background: #101010; border: none; border-top: 1px solid #303034; }
            QPushButton#PickerUse { background: #F4F4F5; color: #101012; border: none; padding: 10px 18px; font-size: 12pt; }
            QPushButton#PickerUse[warning="true"] { background: #F5B82E; }
            QPushButton#PickerUse:disabled { background: #303034; color: #90909B; }
            QPushButton#PickerClose { background: transparent; border: none; color: #A1A1AA; font-size: 20pt; padding: 0; }
        """)
        content = QWidget()
        content.setObjectName("PickerContent")
        shell = QVBoxLayout(content)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        body = QWidget()
        layout = QVBoxLayout(body)
        shell.addWidget(body, 1)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(15)
        title = QLabel("Escolher atalho")
        title.setObjectName("Heading")
        header = QHBoxLayout()
        header.addWidget(title, 1)
        close_button = QPushButton('×')
        close_button.setObjectName('PickerClose')
        close_button.setAccessibleName('Cancelar escolha de atalho')
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.reject)
        header.addWidget(close_button)
        layout.addLayout(header)
        explanation = QLabel("Para Abrir pesquisa. Monte a combinação sem pressionar as teclas.")
        explanation.setObjectName("Subtitle")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        preview = QFrame()
        preview.setObjectName('ShortcutPreview')
        preview.setMinimumHeight(112)
        preview_layout = QHBoxLayout(preview)
        self.preview_keys = ShortcutKeycaps()
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_keys)
        preview_layout.addStretch()
        self.preview_label = QLabel()
        self.preview_label.hide()
        layout.addWidget(preview)
        modifier_label = QLabel("Modificadores")
        modifier_label.setObjectName("PickerLabel")
        layout.addWidget(modifier_label)
        modifier_group = QFrame()
        modifier_group.setObjectName('ModifierGroup')
        modifiers = QHBoxLayout(modifier_group)
        modifiers.setContentsMargins(4, 4, 4, 4)
        modifiers.setSpacing(4)
        self.modifiers = {}
        for name in (("Super", "Alt", "Shift", "Ctrl") if sys.platform == "darwin" else ("Ctrl", "Alt", "Shift", "Super")):
            button = QPushButton(({"Ctrl": "⌘ Command", "Alt": "⌥ Option", "Shift": "⇧ Shift", "Super": "⌃ Control"}.get(name, name)) if sys.platform == "darwin" else name)
            button.setObjectName("ModifierChip")
            button.setCheckable(True)
            button.setAutoDefault(False)
            button.setAccessibleName("Usar modificador " + name)
            self.modifiers[name] = button
            modifiers.addWidget(button, 1)
        layout.addWidget(modifier_group)
        key_label = QLabel("Tecla")
        key_label.setObjectName("PickerLabel")
        layout.addWidget(key_label)
        self.key_combo = Select(heading='Selecionar tecla')
        self.key_combo.setAccessibleName("Tecla do atalho")
        for label, key in (("Espaço", "Space"), ("Enter", "Return"), ("Tab", "Tab"),
                           ("Escape", "Esc"), ("Delete", "Del"), ("Insert", "Ins"),
                           ("Home", "Home"), ("End", "End"), ("Page Up", "PgUp"),
                           ("Page Down", "PgDown"), ("↑", "Up"), ("↓", "Down"),
                           ("←", "Left"), ("→", "Right"), ("+", "+"), (",", ",")):
            self.key_combo.addItem(label, key)
        for key in [*"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", *(f"F{i}" for i in range(1, 36))]:
            self.key_combo.addItem(key, key)
        layout.addWidget(self.key_combo)
        initial = QKeySequence(sequence)
        if not initial.isEmpty():
            combination = initial[0]
            for name, flag in (("Ctrl", Qt.KeyboardModifier.ControlModifier),
                               ("Alt", Qt.KeyboardModifier.AltModifier),
                               ("Shift", Qt.KeyboardModifier.ShiftModifier),
                               ("Super", Qt.KeyboardModifier.MetaModifier)):
                self.modifiers[name].setChecked(bool(combination.keyboardModifiers() & flag))
            key = QKeySequence(combination.key().value).toString(QKeySequence.SequenceFormat.PortableText)
            index = self.key_combo.findData(key)
            if index >= 0:
                self.key_combo.setCurrentIndex(index)
        self.error_label = QLabel()
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        layout.addWidget(self.error_label)
        hint = QLabel("A disponibilidade da combinação será verificada ao aplicar.")
        hint.setObjectName("Subtitle")
        hint.setWordWrap(True)
        self.warning_label = QLabel()
        self.warning_label.setObjectName('PickerWarning')
        self.warning_label.setWordWrap(True)
        layout.addWidget(self.warning_label)
        layout.addWidget(hint)
        layout.addStretch()
        footer = QFrame()
        footer.setObjectName('PickerFooter')
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(28, 16, 28, 16)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.use_button = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.use_button.setText("Usar combinação")
        self.use_button.setObjectName("PickerUse")
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        self.buttons.accepted.connect(self.accept_sequence)
        self.buttons.rejected.connect(self.reject)
        footer_layout.addWidget(self.buttons)
        shell.addWidget(footer)
        self.mount_content(content, maximize=False)
        self.selected_sequence = None
        for button in self.modifiers.values():
            button.toggled.connect(self.update_preview)
        self.key_combo.currentIndexChanged.connect(self.update_preview)
        self.update_preview()

    def chosen_sequence(self):
        names = ["Meta" if name == "Super" else name for name, button in self.modifiers.items()
                 if button.isChecked()]
        return "+".join([*names, self.key_combo.currentData()])

    def update_preview(self):
        sequence = self.chosen_sequence()
        self.preview_label.setText(display_shortcut(sequence))
        self.preview_keys.set_sequence(sequence)
        spotlight = sys.platform == 'darwin' and normalize(sequence) == normalize('Ctrl+Space')
        self.warning_label.setText('Pode conflitar com o Spotlight do macOS. O ClipX não altera esse atalho do sistema; se o registro for recusado, escolha outra combinação.' if spotlight else '')
        self.warning_label.setVisible(spotlight)
        self.use_button.setProperty('warning', spotlight)
        self.use_button.style().unpolish(self.use_button)
        self.use_button.style().polish(self.use_button)
        try:
            self.validate_sequence(sequence)
        except ValueError as exc:
            self.error_label.show()
            self.error_label.setText(str(exc))
            self.error_label.setStyleSheet("color: #ffa0a0;")
            self.use_button.setEnabled(False)
            return
        self.error_label.clear()
        self.error_label.hide()
        self.use_button.setEnabled(True)

    def accept_sequence(self):
        sequence = self.chosen_sequence()
        try:
            self.validate_sequence(sequence)
            self.selected_sequence = normalize(sequence)
        except ValueError as exc:
            self.error_label.show()
            self.error_label.setText(str(exc))
            return
        self.accept()
