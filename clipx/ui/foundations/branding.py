"""Project identity, independent of the monochrome menu-bar glyph."""
from pathlib import Path
from PyQt6.QtGui import QIcon


ICON_PATH = Path(__file__).resolve().parents[2] / 'assets' / 'branding' / 'clipx-icon.png'


def app_icon():
    return QIcon(str(ICON_PATH))
