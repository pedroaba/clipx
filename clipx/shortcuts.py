"""Shared shortcut preferences and portable Qt key sequences."""

import json
import os
from pathlib import Path
import sys
import tempfile

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence


SHORTCUTS = {
    "copy": ("Copiar e colar", "Return"),
    "pin": ("Fixar / desafixar", "Ctrl+P"),
    "delete": ("Excluir item", "Ctrl+D"),
    "delete_alt": ("Excluir item (alternativo)", "Del"),
    "filter": ("Próximo filtro", "Tab"),
    "close": ("Fechar pesquisa", "Esc"),
    "previous": ("Item anterior", "Up"),
    "next": ("Próximo item", "Down"),
}
DEFAULT_SHORTCUTS = {key: default for key, (_, default) in SHORTCUTS.items()}


def normalize(sequence):
    key = QKeySequence(sequence)
    if key.count() != 1 or key[0].key() in (Qt.Key.Key_unknown, Qt.Key.Key_Alt,
                                          Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Meta):
        raise ValueError("Escolha uma única combinação de teclas.")
    # Treat Enter on the numeric keypad as the same action as Return.
    combination = key[0]
    code = combination.key()
    if code == Qt.Key.Key_Enter:
        code = Qt.Key.Key_Return
    modifiers = combination.keyboardModifiers() & ~Qt.KeyboardModifier.KeypadModifier
    if code == Qt.Key.Key_Backtab:
        code = Qt.Key.Key_Tab
        modifiers |= Qt.KeyboardModifier.ShiftModifier
    return QKeySequence(modifiers.value | code.value).toString(QKeySequence.SequenceFormat.PortableText)


def validate_shortcuts(values):
    if not isinstance(values, dict):
        raise ValueError("Configuração de atalhos inválida.")
    result = {}
    used = {}
    for name, (label, default) in SHORTCUTS.items():
        raw = values.get(name, default)
        if not raw:  # An empty field explicitly disables this shortcut.
            result[name] = ""
            continue
        key = normalize(raw)
        if key in used:
            raise ValueError(f'“{label}” e “{used[key]}” usam o mesmo atalho ({key}).')
        combo = QKeySequence(key)[0]
        key_text = QKeySequence(combo.key().value).toString()
        if not combo.keyboardModifiers() and (
            (len(key_text) == 1 and key_text.isprintable()) or combo.key() == Qt.Key.Key_Space
        ):
            raise ValueError(f'Use Ctrl, Alt ou Super com letras em “{label}” para poder pesquisar.')
        result[name] = key
        used[key] = label
    return result


class ShortcutSettings:
    def __init__(self, path=None):
        from clipx.platforms.paths import PlatformPaths
        self.path = Path(path) if path else PlatformPaths().config / "settings.json"

    def load(self):
        try:
            data = json.loads(self.path.read_text())
            return validate_shortcuts(data["shortcuts"])
        except (OSError, ValueError, KeyError, TypeError):
            return DEFAULT_SHORTCUTS.copy()

    def save(self, values):
        values = validate_shortcuts(values)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Keep unrelated preferences when saving shortcuts.
        data = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                if not isinstance(data, dict):
                    data = {}
            except (ValueError, OSError):
                pass
        data["shortcuts"] = values
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write("\n")
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)


def GlobalShortcut(*args, **kwargs):
    """Compatibility constructor; application code uses its injected platform backend."""
    from clipx.platforms import get_platform
    if args or kwargs:
        if sys.platform == "linux":
            from clipx.platforms.linux.shortcuts import LinuxGlobalShortcut
            return LinuxGlobalShortcut(*args, **kwargs)
        from clipx.platforms.macos.shortcuts import MacOSGlobalShortcut
        return MacOSGlobalShortcut(*args, **kwargs)
    return get_platform().shortcuts
