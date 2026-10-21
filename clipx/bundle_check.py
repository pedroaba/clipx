"""Frozen-artifact smoke test using private storage and no system clipboard."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace


def main():
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    from PyQt6.QtWidgets import QApplication
    from clipx.processes import module_command
    from clipx.storage import Storage
    from clipx.shortcuts import ShortcutSettings
    from clipx.ui.pages.clipboard import ClipXMainWindow
    from clipx.ui.pages.preferences import PreferencesDialog
    from clipx.ui.foundations.branding import ICON_PATH
    from clipx.ui.foundations.fonts import install_fonts
    from clipx.platforms.effects import OpaqueWindowEffects
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    with tempfile.TemporaryDirectory(prefix='clipx-smoke-', dir='/tmp') as folder:
        root = Path(folder)
        database = root / 'history.db'
        storage = Storage(database)
        # Exercise the same subprocess route used by wl-paste and capture drivers.
        subprocess.run(module_command('clipx.capture', database), input='build smoke test',
                       text=True, check=True, timeout=30,
                       env={**os.environ, 'CLIPBOARD_STATE': 'data'})
        assert storage.get_clips()[0].content == 'build smoke test'
        from PyQt6.QtNetwork import QLocalServer
        server = QLocalServer()
        assert server.listen(str(root / 'ipc')), server.errorString()
        server.close()
        if sys.platform == 'darwin':
            import AppKit
            import Quartz
            from uuid import uuid4
            from clipx.platforms.macos.clipboard import MacOSClipboardDriver, TEXT_TYPE
            board = AppKit.NSPasteboard.pasteboardWithName_('ClipX.Build.' + uuid4().hex)
            try:
                board.clearContents()
                assert board.setString_forType_('private build fixture', TEXT_TYPE)
                received = []
                result = MacOSClipboardDriver(pasteboard=board).poll(
                    SimpleNamespace(save=received.append, reset=lambda: None))
                assert result.ok and received == ['private build fixture']
            finally:
                board.releaseGlobally()
        else:
            from Xlib import display
        assert ICON_PATH.is_file(), 'Brand icon missing from bundle'
        install_fonts()
        platform = SimpleNamespace(name='test', effects=OpaqueWindowEffects(), clipboard=object(), desktop=object())
        window = ClipXMainWindow(storage, ShortcutSettings(root / 'settings.json'), platform)
        class Shortcuts:
            default_sequence = 'Ctrl+Shift+V'
            modifier_hint = 'Smoke test'
            def read(self): return self.default_sequence
            def from_binding(self, value): return value
            def to_binding(self, value): return value
            def conflicts(self, value): return []
        dialog = PreferencesDialog(window, Shortcuts())
        assert not dialog.windowIcon().isNull(), 'Application icon unavailable'
        for theme in ('dark', 'light'):
            window.apply_preferences({**window.preferences, 'theme': theme})
            app.processEvents()
        assert window.clip_list.count() == 1
        dialog.cancel_changes()
        window.close()
        print(json.dumps({'ok': True, 'platform': sys.platform, 'frozen': bool(getattr(sys, 'frozen', False)),
                          'checks': ['capture-subprocess', 'sqlite', 'local-socket', 'native-driver-import', 'Qt-offscreen', 'fonts', 'icons', 'preferences', 'themes']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
