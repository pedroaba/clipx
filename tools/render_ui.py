"""Render fixture-only UI previews: uv run python tools/render_ui.py [--native].

The script starts a Qt application (offscreen by default, or on the host desktop
with ``--native``), seeds a temporary clipboard history database and a temporary
settings file, and saves screenshots of the shortcuts dialog and clipboard window
to the repository ``artifacts`` directory.
"""
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
    """Shortcut backend stub that returns fixed sample data for previews.

    Attributes:
        default_sequence (str): Sample default shortcut for the current platform.
        modifier_hint (str): Sample modifier legend shown in the dialog.
    """

    default_sequence = 'Ctrl+Shift+V' if sys.platform == 'darwin' else 'Meta+V'
    modifier_hint = ('⌘ Command · ⌥ Option · ⌃ Control · Esc cancela a gravação'
                     if sys.platform == 'darwin' else 'Super = tecla Windows · Esc cancela a gravação')

    def read(self):
        """Return the current shortcut sequence.

        Returns:
            str: The sample sequence defined by ``default_sequence``.
        """
        return self.default_sequence

    def from_binding(self, value):
        """Convert a stored shortcut binding into a display value.

        Args:
            value (str): Stored binding.

        Returns:
            str: The same value, unchanged.
        """
        return value

    def to_binding(self, value):
        """Convert a key sequence into its portable stored representation.

        Args:
            value (object): Value accepted by ``QKeySequence``.

        Returns:
            str: The portable text form of the sequence.
        """
        return QKeySequence(value).toString(QKeySequence.SequenceFormat.PortableText)

    def conflicts(self, value):
        """Report conflicting shortcuts for a value.

        Args:
            value (str): Candidate shortcut sequence; unused by this stub.

        Returns:
            list: An empty list, because the preview has no real conflicts.
        """
        return []

    def pause(self):
        """Stop intercepting shortcuts for the capture subprocess.

        Returns:
            str: The sample sequence resumed later.
        """
        return self.default_sequence

    def resume(self, value):
        """Restore shortcut interception.

        Args:
            value (str): Sequence previously returned by ``pause``; unused.
        """
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
    """Process pending Qt events and save a screenshot of the shortcuts dialog.

    Args:
        name (str): File name written inside the ``artifacts`` directory.
    """
    app.processEvents()
    page.grab().save(str(output / name))


def normal():
    """Capture the default-size dialog and schedule the minimum-size capture."""
    capture('clipx-shortcuts.png')
    page.resize(820, 580)
    QTimer.singleShot(150, minimum)


def minimum():
    """Capture the minimum-size dialog, fill the search field, then filter it."""
    capture('clipx-shortcuts-minimum.png')
    page.resize(1040, 740)
    page.search_field.input.setText('fixar')
    QTimer.singleShot(150, filtered)


def filtered():
    """Capture a search result and switch to a query with no matches."""
    capture('clipx-shortcuts-filtered.png')
    page.search_field.input.setText('inexistente')
    QTimer.singleShot(150, empty)


def empty():
    """Capture the empty search state and start shortcut recording."""
    capture('clipx-shortcuts-empty.png')
    page.search_field.input.clear()
    page.controller.start_recording('pin')
    QTimer.singleShot(150, recording)


def recording():
    """Capture the recording state, close the dialog and show the main window."""
    capture('clipx-shortcuts-recording.png')
    page.controller.stop_recording()
    page.reject()
    window.show()
    QTimer.singleShot(250, clipboard)


def clipboard():
    """Capture the main window, release its effects, and quit the application."""
    window.grab().save(str(output / 'clipx-clipboard-atomic.png'))
    window.platform.effects.remove(window)
    window.close()
    app.quit()


QTimer.singleShot(250, normal)
app.exec()
folder.cleanup()
print('Previews saved to', output)
