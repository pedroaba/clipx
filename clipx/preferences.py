"""Validated UI settings, sharing the existing atomic settings store.

The module defines the permitted UI options, validation that coerces unknown or
invalid values back to defaults, and a settings class that reads and writes the
``ui`` section of the shared ``settings.json`` atomically.
"""

import json
from clipx.shortcuts import ShortcutSettings

OPTIONS = {
    'theme': ('dark', 'light', 'system'), 'scale': (100, 110, 125, 150),
    'density': ('comfortable', 'compact'), 'material': ('platform', 'opaque'),
    'motion': ('system', 'reduce'), 'preview': (True, False), 'lines': (1, 2, 3),
    'metadata': (True, False), 'preview_size': (12, 14, 16, 18), 'syntax': (True, False),
    'position': ('cursor', 'last'), 'remember_size': (True, False),
    'hide_on_blur': (True, False), 'reopen': ('keep', 'clear'),
}
DEFAULT_UI = {key: values[0] for key, values in OPTIONS.items()}
DEFAULT_UI['lines'] = 2


def validate_ui(values):
    """Return a complete UI settings mapping containing only allowed values.

    Every key in ``OPTIONS`` is present in the result. Values must match one of
    the allowed options by both type and equality; anything else falls back to
    the default.

    Args:
        values: Candidate mapping, ignored when it is not a dict.

    Returns:
        dict: Validated settings keyed by option name.
    """
    values = values if isinstance(values, dict) else {}
    return {key: values[key] if key in values and any(type(values[key]) is type(v) and values[key] == v for v in options)
            else DEFAULT_UI[key] for key, options in OPTIONS.items()}


class UISettings(ShortcutSettings):
    """Read and write validated UI preferences in the shared settings file.

    The class reuses the path resolution and atomic write pattern of
    :class:`~clipx.shortcuts.ShortcutSettings` while preserving unrelated
    sections such as shortcuts and window geometry.
    """

    def read_document(self):
        """Read the raw settings document.

        Returns:
            dict: Parsed JSON object, or an empty dict when the file is missing,
            unreadable, invalid JSON, or not a JSON object.
        """
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def load(self):
        """Load validated UI settings from the ``ui`` section.

        Returns:
            dict: Complete validated UI settings with defaults applied.
        """
        return validate_ui(self.read_document().get('ui'))

    def save(self, values, geometry=None, shortcuts=None):
        """Validate and atomically persist UI settings and optional sections.

        The document is written to a temporary file in the settings directory
        and then replaces the settings file. Unrelated existing sections are
        preserved. The temporary file is removed on failure.

        Args:
            values: Candidate UI settings, normalized by ``validate_ui``.
            geometry: Optional window geometry stored under ``window``.
            shortcuts: Optional shortcut mapping stored under ``shortcuts``
                after validation.

        Raises:
            OSError: If the settings directory or file cannot be written.
            ValueError: If ``shortcuts`` fails shortcut validation.
        """
        import tempfile
        from pathlib import Path
        data = self.read_document()
        data['ui'] = validate_ui(values)
        if shortcuts is not None:
            from clipx.shortcuts import validate_shortcuts
            data['shortcuts'] = validate_shortcuts(shortcuts)
        if geometry is not None:
            data['window'] = geometry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as file:
                temporary = Path(file.name)
                json.dump(data, file, ensure_ascii=False, indent=2)
                file.write('\n')
            temporary.replace(self.path)
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
