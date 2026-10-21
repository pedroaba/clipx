"""Render fixture-only UI previews: uv run python tools/render_ui.py [--native]."""
import argparse
import os
from pathlib import Path
import sys
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', action='store_true', help='Use the host desktop rather than offscreen Qt')
args = parser.parse_args()
if not args.native:
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import QApplication
from clipx.platforms import get_platform
from clipx.shortcuts import ShortcutSettings
from clipx.storage import Storage
from clipx.ui.pages.clipboard import ClipXMainWindow
from clipx.ui.pages.shortcuts import ShortcutsDialog


class PreviewShortcuts:
    default_sequence = 'Ctrl+Shift+V' if sys.platform == 'darwin' else 'Meta+V'
    modifier_hint = ('⌘ Command · ⌥ Option · ⌃ Control · Esc cancela a gravação'
                     if sys.platform == 'darwin' else 'Super = tecla Windows · Esc cancela a gravação')

    def read(self):
        return self.default_sequence

    def from_binding(self, value):
        return value

    def to_binding(self, value):
        return QKeySequence(value).toString(QKeySequence.SequenceFormat.PortableText)

    def conflicts(self, value):
        return []

    def pause(self):
        return self.default_sequence

    def resume(self, value):
        pass


app = QApplication([])
app.setApplicationName('ClipX Preview')
app.setQuitOnLastWindowClosed(False)
folder = tempfile.TemporaryDirectory()
root = Path(__file__).resolve().parents[1]
output = root / 'artifacts'
output.mkdir(exist_ok=True)
storage = Storage(Path(folder.name) / 'history.db')
for content, kind, language in (
    ('https://www.raycast.com', 'url', None),
    ('#82B8F8', 'color', None),
    ('def capture_clipboard():\n    return "Olá, mundo"\n', 'code', 'python'),
    ('Notas da migração\nUma interface compartilhada para Linux e macOS.\nPesquisa rápida e histórico local.', 'text', None),
):
    storage.add_clip(content, kind, language)
window = ClipXMainWindow(storage, ShortcutSettings(Path(folder.name) / 'settings.json'))
page = ShortcutsDialog(window, PreviewShortcuts())
page.editors['pin'].setKeySequence(QKeySequence('Ctrl+L'))
page.show()


def capture(name):
    app.processEvents()
    page.grab().save(str(output / name))


def normal():
    capture('clipx-shortcuts.png')
    page.resize(820, 580)
    QTimer.singleShot(150, minimum)


def minimum():
    capture('clipx-shortcuts-minimum.png')
    page.resize(1040, 740)
    page.search_field.input.setText('fixar')
    QTimer.singleShot(150, filtered)


def filtered():
    capture('clipx-shortcuts-filtered.png')
    page.search_field.input.setText('inexistente')
    QTimer.singleShot(150, empty)


def empty():
    capture('clipx-shortcuts-empty.png')
    page.search_field.input.clear()
    page.controller.start_recording('pin')
    QTimer.singleShot(150, recording)


def recording():
    capture('clipx-shortcuts-recording.png')
    page.controller.stop_recording()
    page.reject()
    window.show()
    QTimer.singleShot(250, clipboard)


def clipboard():
    window.grab().save(str(output / 'clipx-clipboard-atomic.png'))
    window.platform.effects.remove(window)
    window.close()
    app.quit()


QTimer.singleShot(250, normal)
app.exec()
folder.cleanup()
print('Previews saved to', output)
