"""Fixture-only preferences previews; never touches the global clipboard or shortcuts."""
import os
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
if '--native' not in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
from clipx.shortcuts import ShortcutSettings
from clipx.storage import Storage
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.pages.preferences import PreferencesDialog
from clipx.platforms.effects import OpaqueWindowEffects

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    from clipx.platforms import get_platform
    platform = get_platform() if '--native' in sys.argv else SimpleNamespace(name='test', effects=OpaqueWindowEffects(), clipboard=Mock(), desktop=Mock())
    window = ClipXMainWindow(Storage(root / 'history.db'), ShortcutSettings(root / 'settings.json'), platform)
    window.storage.add_clip('Notas de exemplo\nUma interface para ler com conforto.\nTerceira linha de conteúdo.')
    window.storage.add_clip('def greet(name):\n    return f"Olá, {name}"', 'code', 'python')
    backend = Mock()
    backend.read.return_value = 'Meta+V'
    backend.from_binding.side_effect = lambda value: value
    backend.to_binding.side_effect = lambda value: value
    backend.default_sequence = 'Meta+V'
    backend.modifier_hint = 'Atalhos de exemplo'
    page = PreferencesDialog(window, backend)
    output = Path(__file__).resolve().parents[1] / 'artifacts'
    for theme in ('dark', 'light'):
        page.controls['theme'].setCurrentIndex(page.controls['theme'].findData(theme))
        page.apply_changes()
        page.resize(1040, 740)
        page.show()
        for section in ('appearance', 'content', 'window', 'shortcuts'):
            page.select_section(section)
            app.processEvents()
            page.grab().save(str(output / f'preferences-{theme}-{section}.png'))
        page.select_section('appearance')
        page.controls['scale'].setCurrentIndex(page.controls['scale'].findData(150))
        page.apply_changes()
        page.resize(820, 580)
        app.processEvents()
        page.grab().save(str(output / f'preferences-{theme}-minimum.png'))
        window.show()
        app.processEvents()
        window.grab().save(str(output / f'clipboard-{theme}-scaled.png'))
        window.hide()
        page.controls['scale'].setCurrentIndex(page.controls['scale'].findData(100))
        page.apply_changes()
    page.cancel_changes()
    window.close()
