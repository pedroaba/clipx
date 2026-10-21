"""Validated UI settings, sharing the existing atomic settings store."""
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
    values = values if isinstance(values, dict) else {}
    return {key: values[key] if key in values and any(type(values[key]) is type(v) and values[key] == v for v in options)
            else DEFAULT_UI[key] for key, options in OPTIONS.items()}


class UISettings(ShortcutSettings):
    def read_document(self):
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def load(self):
        return validate_ui(self.read_document().get('ui'))

    def save(self, values, geometry=None, shortcuts=None):
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
