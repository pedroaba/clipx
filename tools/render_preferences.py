"""Fixture-only preferences previews; never touches the global clipboard or shortcuts.

Builds an offscreen (or, with ``--native``, host desktop) Qt application with a
temporary history database and settings file, then saves screenshots of each
preferences section in dark and light themes, plus scaled clipboard previews, to
the ``artifacts`` directory. Everything is torn down when the script exits.
"""
import os
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock
if '--native' not in sys.argv:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from clipx.shortcuts import ShortcutSettings
from clipx.storage import Storage
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.pages.preferences import PreferencesDialog
from clipx.platforms.effects import OpaqueWindowEffects

app = QApplication([])
app.setQuitOnLastWindowClosed(False)
maintenance_only = '--maintenance' in sys.argv
confirmations_only = '--confirmations' in sys.argv
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
        page.resize(1040, 820 if maintenance_only else 740)
        page.show()
        if confirmations_only:
            from clipx.maintenance import MaintenanceResult, PruneOptions
            from clipx.ui.organisms.maintenance_confirmation import MaintenanceConfirmation, prune_confirmation, uninstall_confirmation
            # Explicit preview fixtures, unrelated to the user's real history.
            estimate = MaintenanceResult(items=20, files=1, bytes=220243,
                                         paths=[str(Path.home() / 'Library/Application Support/ClipX'),
                                                str(Path.home() / 'Library/Preferences/ClipX')])
            for name, spec in [('prune', prune_confirmation(PruneOptions('all', 'content'), estimate)),
                               ('uninstall', uninstall_confirmation(estimate))]:
                alert = MaintenanceConfirmation(spec, window.preferences, page)
                alert.show()
                app.processEvents()
                alert.grab().save(str(output / f'confirmation-{theme}-{name}.png'))
                alert.reject()
                alert.deleteLater()
            continue
        sections = ('maintenance',) if maintenance_only else ('appearance', 'content', 'window', 'shortcuts')
        for section in sections:
            page.select_section(section)
            if section == 'maintenance':
                page.maintenance_page.analyze_data()
                for _ in range(500):
                    QTest.qWait(10)
                    if not page.maintenance_page.busy:
                        break
                else:
                    raise TimeoutError('A análise dos dados de exemplo não terminou.')
            app.processEvents()
            page.grab().save(str(output / f'preferences-{theme}-{section}.png'))
        if maintenance_only:
            continue
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
