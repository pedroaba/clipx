"""Project identity, independent of the monochrome menu-bar glyph.

Resolves the bundled full-color application icon used for windows and desktop
entries.
"""
from pathlib import Path
from PyQt6.QtGui import QIcon


ICON_PATH = Path(__file__).resolve().parents[2] / 'assets' / 'branding' / 'clipx-icon.png'


def app_icon():
    """Load the bundled ClipX brand icon.

    Returns:
        QIcon: Icon built from the PNG asset, independent of the menu-bar glyph.
    """
    return QIcon(str(ICON_PATH))
