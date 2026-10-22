"""GNOME global shortcut backend.

Reads and writes ClipX's custom keybinding through the ``gsettings`` command
line tool under the GNOME media-keys schema. GNOME stores accelerators in its
own ``<Control><Alt>key`` syntax, so this module translates between that syntax
and the portable sequences used by the rest of ClipX. It also detects and, with
explicit approval, reassigns conflicting system keybindings.
"""
import ast
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
from clipx.processes import module_command

import re
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from clipx.shortcuts import normalize


def from_gnome(binding):
    """Convert a GNOME accelerator description into a normalized key sequence.

    Modifier tags such as ``<Super>``, ``<Primary>`` or ``<Control>`` are mapped
    to their portable names, and the remaining key name is translated from the
    X11/GNOME spelling (for example ``Page_Up`` or ``ISO_Left_Tab``).

    Args:
        binding (str | None): GNOME accelerator string, or a falsy value for no
            binding.

    Returns:
        str: Normalized sequence, or an empty string when ``binding`` is falsy.
    """
    if not binding:
        return ""
    tags = re.findall(r"<([^>]+)>", binding)
    names = {"super": "Meta", "meta": "Meta", "primary": "Ctrl", "control": "Ctrl",
             "ctrl": "Ctrl", "alt": "Alt", "shift": "Shift"}
    modifiers = [names[tag.lower()] for tag in tags]
    key = re.sub(r"<[^>]+>", "", binding)
    if key == "ISO_Left_Tab" and "Shift" not in modifiers:
        modifiers.append("Shift")
    key = {"space": "Space", "Page_Up": "PgUp", "Page_Down": "PgDown",
           "BackSpace": "Backspace", "Escape": "Esc", "Delete": "Del",
           "ISO_Left_Tab": "Tab", "plus": "+", "comma": ","}.get(key, key)
    return normalize("+".join([*modifiers, key]))


def to_gnome(sequence):
    """Convert a portable key sequence into a GNOME accelerator description.

    The sequence is parsed with Qt's key-sequence parser and rebuilt as
    ``<Control>``/``<Alt>``/``<Shift>``/``<Super>`` tags followed by the GNOME
    key name.

    Args:
        sequence (str): Portable key sequence, for example ``Ctrl+V``.

    Returns:
        str: GNOME accelerator string, or an empty string for an empty sequence.

    Raises:
        ValueError: If the sequence has no modifier, if it would interfere with
            typing (only Shift plus a printable key), or if the key is not on
            GNOME's supported list. Messages are user-facing Portuguese text.
    """
    if not sequence:
        return ""
    combo = QKeySequence(normalize(sequence))[0]
    tags = ""
    for modifier, name in ((Qt.KeyboardModifier.ControlModifier, "Control"),
                           (Qt.KeyboardModifier.AltModifier, "Alt"),
                           (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                           (Qt.KeyboardModifier.MetaModifier, "Super")):
        if combo.keyboardModifiers() & modifier:
            tags += f"<{name}>"
    if not tags:
        raise ValueError("O atalho global precisa incluir Ctrl, Alt, Shift ou Super.")
    key = QKeySequence(combo.key().value).toString(QKeySequence.SequenceFormat.PortableText)
    if not (combo.keyboardModifiers() & (Qt.KeyboardModifier.ControlModifier
                                         | Qt.KeyboardModifier.AltModifier
                                         | Qt.KeyboardModifier.MetaModifier)) and (
        (len(key) == 1 and key.isprintable()) or key == "Space"
    ):
        raise ValueError("Use Ctrl, Alt ou Super no atalho global para não interferir na digitação.")
    supported_names = {"Space", "PgUp", "PgDown", "Backspace", "Esc", "Del", "Ins",
                       "Tab", "Return", "Up", "Down", "Left", "Right", "Home", "End",
                       "Pause", "Print", "ScrollLock", "NumLock", "+", ","}
    if not re.fullmatch(r"[A-Za-z0-9]|F(?:[1-9]|[12][0-9]|3[0-5])", key) and key not in supported_names:
        raise ValueError("Essa tecla não é suportada no atalho global. Escolha uma letra, número ou tecla F.")
    key = {"Space": "space", "PgUp": "Page_Up", "PgDown": "Page_Down",
           "Backspace": "BackSpace", "Esc": "Escape", "Del": "Delete",
           "+": "plus", ",": "comma", "Ins": "Insert"}.get(key, key)
    return tags + (key.lower() if len(key) == 1 else key)


class LinuxGlobalShortcut:
    """Manage ClipX's global shortcut through GNOME's custom keybindings.

    The backend shells out to ``gsettings`` and therefore works with the GNOME
    settings daemon rather than registering a grab directly with X11 or
    Wayland. All mutating operations verify the value GNOME reports back and
    raise ``RuntimeError`` when the change is not confirmed.

    Attributes:
        SCHEMA (str): Media-keys schema that owns custom keybindings.
        PATH (str): Relative keybinding path reserved for ClipX.
        CUSTOM (str): Relative schema prefix for one custom keybinding.
        SYSTEM_SCHEMAS (tuple[str, ...]): Schemas scanned for conflicts.
        recovery_path (Path): JSON file used to restore a paused binding.
        modifier_hint (str): User-facing hint shown beside the recorder.
        to_binding (staticmethod): Alias of :func:`to_gnome`.
        from_binding (staticmethod): Alias of :func:`from_gnome`.
        default_sequence (str): Default shortcut used by ClipX.
        portable_bindings (bool): Whether bindings are stored portably; always
            ``False`` because GNOME keeps its own accelerator syntax.
    """
    SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
    PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipx/"
    CUSTOM = SCHEMA + ".custom-keybinding:"
    SYSTEM_SCHEMAS = (
        "org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings",
        "org.gnome.mutter.keybindings", "org.gnome.mutter.wayland.keybindings", SCHEMA,
    )

    def __init__(self, recovery_path=None):
        """Initialize the backend and choose the recovery file location.

        Args:
            recovery_path (str | os.PathLike | None): Explicit path for the
                recovery JSON file. When omitted, the file lives under
                ``XDG_CONFIG_HOME`` (or ``~/.config``) in ``clipx``.
        """
        self.recovery_path = Path(recovery_path) if recovery_path else Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ) / "clipx" / "shortcut-recording.json"

    def pause(self):
        """Pause only ClipX's binding while the user explicitly records keys.

        The current binding is flushed to the recovery file before GNOME's
        binding is cleared, so an interrupted recording can be undone later.

        Returns:
            str: The paused binding, or an empty string when nothing was bound.

        Raises:
            RuntimeError: If reading or clearing the GNOME binding fails.
            OSError: If the recovery file cannot be written.
        """
        self.recover()
        binding = self.read()
        if not binding:
            return ""
        self.recovery_path.parent.mkdir(parents=True, exist_ok=True)
        with self.recovery_path.open("w") as file:
            json.dump({"binding": binding}, file)
            file.flush()
            os.fsync(file.fileno())
        try:
            self.write("")
        except (RuntimeError, OSError):
            self.recover()
            raise
        return binding

    def resume(self, binding):
        """Restore a binding after recording and remove the recovery file.

        If GNOME already has a binding (for example one the user set while
        recording was paused), that value is kept and ``binding`` is ignored.

        Args:
            binding (str): Previously paused binding to restore when the current
                binding is empty.
        """
        if not binding:
            return
        # Respect changes made in GNOME settings while recording was paused.
        if not self.read():
            self.write(binding)
        self.recovery_path.unlink(missing_ok=True)

    def recover(self):
        """Restore a paused binding after an interrupted recording session.

        Does nothing when no recovery file exists. The file is removed by
        :meth:`resume`.

        Raises:
            RuntimeError: If the recovery file has no valid non-empty string
                binding, or if restoring the binding fails.
        """
        if self.recovery_path.exists():
            data = json.loads(self.recovery_path.read_text())
            binding = data.get("binding")
            if not isinstance(binding, str) or not binding:
                raise RuntimeError("Registro de recuperação do atalho inválido.")
            self.resume(binding)

    def run(self, *args):
        """Run a ``gsettings`` command and return its trimmed standard output.

        The subprocess is bounded to a three second timeout and its output is
        captured.

        Args:
            *args (str): Arguments forwarded to ``gsettings``.

        Returns:
            str: Stripped standard output of the command.

        Raises:
            RuntimeError: If the executable is missing, the call times out, or
                ``gsettings`` exits with a non-zero status.
        """
        try:
            result = subprocess.run(["gsettings", *args], capture_output=True,
                                    text=True, timeout=3, check=True)
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("Não foi possível acessar os atalhos do GNOME nesta sessão.") from exc

    def get(self, schema, key):
        """Read and parse a typed ``gsettings`` value.

        A leading ``@as `` type annotation is stripped before parsing with
        :func:`ast.literal_eval`, so string lists come back as Python lists.

        Args:
            schema (str): Schema identifier or relative schema and path.
            key (str): Key to read.

        Returns:
            object: Parsed value produced by ``ast.literal_eval``.

        Raises:
            RuntimeError: If ``gsettings`` cannot be queried.
            ValueError: If the reported value is not a Python literal.
        """
        value = self.run("get", schema, key)
        if value.startswith("@as "):
            value = value[4:]
        return ast.literal_eval(value)

    def read(self):
        """Read ClipX's current GNOME accelerator.

        Returns:
            str: GNOME accelerator description, or an empty string when unset.

        Raises:
            RuntimeError: If ``gsettings`` cannot be queried.
        """
        return self.get(self.CUSTOM + self.PATH, "binding")

    def conflicts(self, sequence):
        """List display names of bindings that would conflict with a sequence.

        Args:
            sequence (str): Portable key sequence to check.

        Returns:
            list[str]: Names reported by :meth:`conflict_bindings`.
        """
        return [item["name"] for item in self.conflict_bindings(sequence)]

    def conflict_bindings(self, sequence):
        """Find system and custom bindings that use the requested sequence.

        Every schema in ``SYSTEM_SCHEMAS`` is dumped with
        ``gsettings list-recursively``; string and string-list values that
        normalize to ``sequence`` are collected, together with ClipX's sibling
        custom keybindings. Schemas missing from a GNOME installation are
        skipped, and entries whose GNOME syntax cannot be normalized are
        ignored.

        Args:
            sequence (str): Portable key sequence to look for.

        Returns:
            list[dict]: One entry per conflicting binding, with the keys
                ``schema``, ``key``, ``value`` and ``name``.

        Raises:
            RuntimeError: If the custom keybinding list cannot be read.
        """
        wanted = normalize(sequence)
        found = []
        seen = set()

        def matches(binding):
            """Report whether a single GNOME binding equals the wanted sequence."""
            try:
                return bool(binding) and from_gnome(binding) == wanted
            except (ValueError, KeyError, TypeError):
                return False

        def add(schema, key, value, name):
            """Record a conflicting key at most once, keyed by schema and key."""
            bindings = value if isinstance(value, list) else [value]
            identity = (schema, key)
            if identity not in seen and any(matches(binding) for binding in bindings):
                seen.add(identity)
                found.append({"schema": schema, "key": key, "value": value, "name": name})

        for schema in self.SYSTEM_SCHEMAS:
            try:
                lines = self.run("list-recursively", schema)
            except RuntimeError:
                continue  # Some GNOME versions do not provide every schema.
            for line in lines.splitlines():
                parts = line.split(maxsplit=2)
                if len(parts) != 3:
                    continue
                try:
                    value = ast.literal_eval(parts[2].removeprefix("@as "))
                except (ValueError, SyntaxError):
                    continue
                if isinstance(value, (str, list)):
                    add(parts[0], parts[1], value, parts[1])
        for path in self.get(self.SCHEMA, "custom-keybindings"):
            if path != self.PATH:
                binding = self.get(self.CUSTOM + path, "binding")
                if matches(binding):
                    add(self.CUSTOM + path, "binding", binding,
                        self.get(self.CUSTOM + path, "name") or "outro atalho")
        return found

    def restore_conflicts(self, changes):
        """Put back bindings that :meth:`reassign` cleared.

        Each change is restored in reverse order, but only when the current
        value is still the replacement written by ClipX. A value changed by
        another application is reported instead of overwritten.

        Args:
            changes (list[dict]): Change records produced by :meth:`reassign`,
                each containing ``schema``, ``key``, ``name``, ``value`` and
                ``replacement``.

        Raises:
            RuntimeError: If the value was changed elsewhere, if the restore is
                not confirmed by GNOME, or if any binding could not be restored.
                The message lists the affected names.
        """
        errors = []
        for item in reversed(changes):
            try:
                current = self.get(item["schema"], item["key"])
                if current == item["replacement"]:
                    self.run("set", item["schema"], item["key"], repr(item["value"]))
                    if self.get(item["schema"], item["key"]) != item["value"]:
                        raise RuntimeError("Restauração não confirmada")
                elif current != item["value"]:
                    raise RuntimeError("A configuração foi alterada por outro aplicativo")
            except RuntimeError:
                errors.append(item["name"])
        if errors:
            raise RuntimeError("Não foi possível restaurar: " + ", ".join(errors))

    def reassign(self, binding, approved_conflicts):
        """Transfer only the approved combination, preserving other bindings.

        Before changing anything, the current conflicts must equal
        ``approved_conflicts``; otherwise the user has to review them again. For
        each conflicting key the matching accelerator is removed (or the whole
        key cleared for scalar values), then ClipX's binding is written. On any
        failure the previous ClipX binding and every touched key are restored,
        and the collected errors are combined into one exception.

        Args:
            binding (str): GNOME accelerator description to assign to ClipX.
            approved_conflicts (list[dict]): Conflict records the user approved,
                as returned by :meth:`conflict_bindings`.

        Returns:
            list[dict]: Applied change records, each with an added
                ``replacement`` value, suitable for :meth:`restore_conflicts`.

        Raises:
            RuntimeError: If the conflicts changed, a system binding changed, a
                write or verification failed, or restoration failed.
        """
        wanted = from_gnome(binding)
        current = self.conflict_bindings(wanted)
        if current != approved_conflicts:
            raise RuntimeError("Os conflitos mudaram. Clique em Aplicar para revisá-los novamente.")
        previous = self.read()
        changes = []
        try:
            for item in current:
                if self.get(item["schema"], item["key"]) != item["value"]:
                    raise RuntimeError("Os atalhos do sistema mudaram. Tente aplicar novamente.")
                values = item["value"] if isinstance(item["value"], list) else [item["value"]]
                remaining = []
                for value in values:
                    try:
                        match = from_gnome(value) == wanted
                    except (ValueError, KeyError):
                        match = False
                    if not match:
                        remaining.append(value)
                replacement = remaining if isinstance(item["value"], list) else ""
                change = {**item, "replacement": replacement}
                changes.append(change)
                self.run("set", item["schema"], item["key"], repr(replacement))
                if self.get(item["schema"], item["key"]) != replacement:
                    raise RuntimeError("O GNOME não confirmou a liberação do atalho.")
            self.write(binding)
            return changes
        except (RuntimeError, OSError) as exc:
            errors = [str(exc)]
            try:
                if self.read() == binding:
                    self.write(previous)
            except RuntimeError as restore_error:
                errors.append(str(restore_error))
            try:
                self.restore_conflicts(changes)
            except RuntimeError as restore_error:
                errors.append(str(restore_error))
            raise RuntimeError(" ".join(errors)) from exc

    def write(self, binding):
        """Write ClipX's accelerator, registering the custom keybinding if needed.

        On first use the keybinding entry is created with a name and a launch
        command (the repository launcher when present, otherwise a module
        command), and its path is appended to the media-keys
        ``custom-keybindings`` list.

        Args:
            binding (str): GNOME accelerator description; an empty string
                disables the shortcut.

        Raises:
            RuntimeError: If GNOME does not confirm the written binding.
        """
        paths = self.get(self.SCHEMA, "custom-keybindings")
        schema = self.CUSTOM + self.PATH
        if self.PATH not in paths:
            self.run("set", schema, "name", repr("ClipX Clipboard Manager"))
            launcher = Path(__file__).resolve().parents[3] / "bin" / "clipx"
            command = ([str(launcher), "show"] if launcher.exists()
                       else module_command("clipx.main", "show"))
            self.run("set", schema, "command", repr(shlex.join(command)))
        self.run("set", schema, "binding", repr(binding))
        if self.read() != binding:
            raise RuntimeError("O GNOME não confirmou a alteração do atalho.")
        if self.PATH not in paths:
            self.run("set", self.SCHEMA, "custom-keybindings", repr([*paths, self.PATH]))

    modifier_hint = "Super = tecla Windows · Esc cancela a gravação · × desativa o atalho"
    to_binding = staticmethod(to_gnome)
    from_binding = staticmethod(from_gnome)
    default_sequence = "Meta+V"
    portable_bindings = False

    def start(self, callback):
        """Recover any interrupted recording before the shortcut becomes active.

        GNOME itself owns the accelerator, so no callback is registered here.

        Args:
            callback (callable): Activation callback supplied by the generic
                shortcut interface; unused on Linux.

        Raises:
            RuntimeError: If a pending recovery cannot be completed.
        """
        self.recover()

    def stop(self):
        """Do nothing, because GNOME keeps the shortcut registered after exit."""
        pass
