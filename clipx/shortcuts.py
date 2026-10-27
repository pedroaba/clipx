"""Shared shortcut preferences and portable Qt key sequences.

The module defines the configurable shortcut catalog, normalization and
validation helpers, an atomic JSON settings store, and a compatibility factory
for platform-specific global shortcut backends.
"""

from clipx.maintenance_lock import writer
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
    """Validate one shortcut and return its portable text form.

    Modifier-only keys, unknown keys, multi-step sequences, and keypad-``Enter``
    or ``Backtab`` presses are normalized to their portable equivalents.

    Args:
        sequence: Single key combination, as text or a Qt key sequence.

    Returns:
        str: Portable text representation of the combination.

    Raises:
        ValueError: If the input is not a single usable key combination.
    """
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
    """Validate a shortcut mapping and return normalized bindings.

    Missing entries fall back to their defaults and empty entries explicitly
    disable a shortcut. Each binding is normalized and checked for duplicates
    and for unmodified printable keys or Space, which would block typing in the
    search field.

    Args:
        values: Mapping of shortcut names to key combinations. It must be a
            dict; unknown names are ignored and absent names use defaults.

    Returns:
        dict: Normalized portable key sequence per shortcut name, with empty
        strings for disabled shortcuts.

    Raises:
        ValueError: If ``values`` is not a dict, a binding is invalid, two
            shortcuts collide, or an unmodified printable key is used.
    """
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
    """Load and save shortcut bindings in the shared JSON settings file.

    Writes are atomic: a temporary file is created in the settings directory,
    then moved over the destination. Unrelated settings keys are preserved.
    """

    def __init__(self, path=None):
        """Resolve the settings file path.

        Args:
            path: Optional explicit settings path. When omitted, the platform
                config directory's ``settings.json`` is used.
        """
        from clipx.platforms.paths import PlatformPaths
        self.path = Path(path) if path else PlatformPaths().config / "settings.json"

    def load(self):
        """Load validated shortcuts, falling back to defaults.

        Returns:
            dict: Normalized shortcut bindings, or a copy of
            ``DEFAULT_SHORTCUTS`` when the file is missing or invalid.
        """
        try:
            data = json.loads(self.path.read_text())
            return validate_shortcuts(data["shortcuts"])
        except (OSError, ValueError, KeyError, TypeError):
            return DEFAULT_SHORTCUTS.copy()

    @writer
    def save(self, values):
        """Validate and atomically save shortcut bindings.

        Existing unrelated settings are preserved. The temporary file is
        removed if writing or replacing the destination fails.

        Args:
            values: Shortcut mapping to validate and store.

        Raises:
            OSError: If the settings directory or file cannot be written.
            ValueError: If the shortcut mapping is invalid.
        """
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
    """Construct a platform global shortcut backend for compatibility.

    Application code normally uses the injected platform backend. When
    arguments are supplied, this factory creates the Linux or macOS backend
    directly based on ``sys.platform``; otherwise it returns the shortcuts
    backend of the resolved platform.

    Args:
        *args: Positional arguments forwarded to the backend constructor.
        **kwargs: Keyword arguments forwarded to the backend constructor.

    Returns:
        The platform global shortcut backend.
    """
    from clipx.platforms import get_platform
    if args or kwargs:
        if sys.platform == "linux":
            from clipx.platforms.linux.shortcuts import LinuxGlobalShortcut
            return LinuxGlobalShortcut(*args, **kwargs)
        from clipx.platforms.macos.shortcuts import MacOSGlobalShortcut
        return MacOSGlobalShortcut(*args, **kwargs)
    return get_platform().shortcuts
