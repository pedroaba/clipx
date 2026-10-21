"""GNOME global shortcut backend."""
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
    SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
    PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/clipx/"
    CUSTOM = SCHEMA + ".custom-keybinding:"
    SYSTEM_SCHEMAS = (
        "org.gnome.desktop.wm.keybindings", "org.gnome.shell.keybindings",
        "org.gnome.mutter.keybindings", "org.gnome.mutter.wayland.keybindings", SCHEMA,
    )

    def __init__(self, recovery_path=None):
        self.recovery_path = Path(recovery_path) if recovery_path else Path(
            os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
        ) / "clipx" / "shortcut-recording.json"

    def pause(self):
        """Pause only ClipX's binding while the user explicitly records keys."""
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
        if not binding:
            return
        # Respect changes made in GNOME settings while recording was paused.
        if not self.read():
            self.write(binding)
        self.recovery_path.unlink(missing_ok=True)

    def recover(self):
        """Restore a paused binding after an interrupted recording session."""
        if self.recovery_path.exists():
            data = json.loads(self.recovery_path.read_text())
            binding = data.get("binding")
            if not isinstance(binding, str) or not binding:
                raise RuntimeError("Registro de recuperação do atalho inválido.")
            self.resume(binding)

    def run(self, *args):
        try:
            result = subprocess.run(["gsettings", *args], capture_output=True,
                                    text=True, timeout=3, check=True)
            return result.stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise RuntimeError("Não foi possível acessar os atalhos do GNOME nesta sessão.") from exc

    def get(self, schema, key):
        value = self.run("get", schema, key)
        if value.startswith("@as "):
            value = value[4:]
        return ast.literal_eval(value)

    def read(self):
        return self.get(self.CUSTOM + self.PATH, "binding")

    def conflicts(self, sequence):
        return [item["name"] for item in self.conflict_bindings(sequence)]

    def conflict_bindings(self, sequence):
        wanted = normalize(sequence)
        found = []
        seen = set()

        def matches(binding):
            try:
                return bool(binding) and from_gnome(binding) == wanted
            except (ValueError, KeyError, TypeError):
                return False

        def add(schema, key, value, name):
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
        """Transfer only the approved combination, preserving other bindings."""
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
        self.recover()

    def stop(self):
        pass
