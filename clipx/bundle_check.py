"""Frozen-artifact smoke test using private storage and no system clipboard.

The script runs entirely offscreen against a temporary directory, exercising the
capture subprocess, SQLite storage, local sockets, native driver imports, Qt
widgets, fonts, icons, preferences, and themes to verify a packaged build.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace


def main():
    """Run the offscreen smoke test against temporary, private state.

    The test forces the offscreen Qt platform, verifies the capture subprocess
    and storage round trip, checks local socket availability, imports or
    exercises the native clipboard driver per platform, then builds the main
    window and preferences dialog to check icons, fonts, and themes. A JSON
    summary is printed on success.

    Returns:
        int: Zero when every check passes.

    Raises:
        AssertionError: If any check fails.
        subprocess.CalledProcessError: If the capture subprocess fails.
        subprocess.TimeoutExpired: If the capture subprocess exceeds 30 seconds.
    """
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
        from clipx import update_install
        assert (Path(update_install.__file__).parent / 'scripts/updates/supervisor.sh').is_file(), 'Update helper missing from bundle'
        from clipx.updates import tls_context
        assert tls_context().get_ca_certs(), 'HTTPS certificate store unavailable'
        install_fonts()
        platform = SimpleNamespace(name='test', effects=OpaqueWindowEffects(), clipboard=object(), desktop=object())
        window = ClipXMainWindow(storage, ShortcutSettings(root / 'settings.json'), platform)
        class Shortcuts:
            """Minimal shortcut backend stub used by the preferences dialog."""

            default_sequence = 'Ctrl+Shift+V'
            modifier_hint = 'Smoke test'

            def read(self):
                """Return the stub's default sequence.

                Returns:
                    str: The default shortcut sequence.
                """
                return self.default_sequence

            def from_binding(self, value):
                """Return a binding unchanged.

                Args:
                    value: Binding to pass through.

                Returns:
                    The same binding.
                """
                return value

            def to_binding(self, value):
                """Return a binding unchanged.

                Args:
                    value: Binding to pass through.

                Returns:
                    The same binding.
                """
                return value

            def conflicts(self, value):
                """Report no conflicting shortcuts.

                Args:
                    value: Candidate binding, ignored.

                Returns:
                    list: Always an empty list.
                """
                return []
        dialog = PreferencesDialog(window, Shortcuts())
        assert not dialog.windowIcon().isNull(), 'Application icon unavailable'
        dialog.select_section('updates')
        assert dialog.updates_page.service.worker is None, 'Updates must remain manual'
        assert dialog.footer.reset.isHidden(), 'Updates has no resettable settings'
        for theme in ('dark', 'light'):
            window.apply_preferences({**window.preferences, 'theme': theme})
            app.processEvents()
        assert window.clip_list.count() == 1
        dialog.cancel_changes()
        window.close()
        print(json.dumps({'ok': True, 'platform': sys.platform, 'frozen': bool(getattr(sys, 'frozen', False)),
                          'checks': ['capture-subprocess', 'sqlite', 'local-socket', 'native-driver-import', 'Qt-offscreen', 'fonts', 'icons', 'preferences', 'themes', 'updates-helper', 'updates-page']}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
